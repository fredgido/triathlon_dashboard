import datetime
import itertools
import json
import os
import re
import string
import typing
from concurrent.futures import ThreadPoolExecutor

import backoff
import country_converter
import httpx
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

country_converter.logging.getLogger().setLevel(country_converter.logging.CRITICAL)


# config response
class ConfigResponseContest(typing.TypedDict):
    key: str
    contests: dict[str, str]


class ConfigResponseSplit(typing.TypedDict):
    ID: int
    Name: str
    Label: str
    SplitType: int
    Contest: int
    TypeOfSport: int


class ConfigResponseListEntry(typing.TypedDict):
    Name: str
    Mode: str
    Contest: str
    ShowAs: str
    Format: str
    Live: int
    Sortable: int
    Leader: int
    Details: str
    ID: str


class ConfigResponse(typing.TypedDict):
    key: str
    eventname: str
    contests: dict[str, str]
    splits: list[ConfigResponseSplit]
    lists: list[ConfigResponseListEntry]


# list participants response
class ParticipantListResponse(typing.TypedDict):
    data: dict[str, list[str]]


cc = country_converter.CountryConverter()


def get_english_translation(text):
    if isinstance(text, str) and "{" in text:
        match = re.search(r"EN:([^|}]+)", text)
        return match.group(1).strip() if match else text
    return text


@backoff.on_exception(backoff.expo, (httpx.RequestError,), max_time=60)
def fetch_athlete_data() -> tuple[ConfigResponse, dict[str, ParticipantListResponse]]:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "dnt": "1",
        "origin": "https://zurichcitytriathlon.ch",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://zurichcitytriathlon.ch/",
        "sec-ch-ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    }

    config_url = "https://my.raceresult.com/307885/RRPublish/data/config"
    config_params = {"page": "participants", "noVisitor": "1"}

    list_url = "https://my.raceresult.com/307885/RRPublish/data/list"
    list_params = {
        "key": "4e6f7163c82a088408a57645785fd923",
        "listname": "000-Startlists|Waitlist",
        "page": "participants",
        "contest": "0",
        "r": "all",
        "l": "0",
    }

    with httpx.Client(http2=True, headers=headers) as client:
        config_response = client.get(config_url, params=config_params)
        config_response.raise_for_status()
        config_data: ConfigResponse = config_response.json()

        participant_lists: dict[str, ParticipantListResponse] = {}
        with ThreadPoolExecutor() as executor:
            futures = {}
            for list_entry in config_data["lists"]:
                params = {**list_params, "listname": list_entry["Name"], "key": config_data["key"]}
                futures[list_entry["Name"]] = executor.submit(lambda p: client.get(list_url, params=p).json(), params)

            for name, future in futures.items():
                response = future.result()
                participant_lists[name] = response

        return config_data, participant_lists


def process_athlete_data(athlete_list_per_category: dict[str, list[str]]) -> pd.DataFrame:
    athlete_rows_lists_per_category = [
        [(*athlete, category) for athlete in athletes] for category, athletes in athlete_list_per_category.items()
    ]
    athlete_rows = itertools.chain(*athlete_rows_lists_per_category)

    # fmt: off
    columns = [
        "bib", "contest", "name", "gender", "start", "age_group", "club",
        "company", "flag_icon", "country", "year_born", "contest_category"
    ]
    # fmt: on

    df = pd.DataFrame(athlete_rows, columns=columns).drop(columns="flag_icon")

    df = df.replace({None: pd.NA, "": pd.NA})
    df = df.map(lambda v: v.strip() if isinstance(v, str) else v).replace("", pd.NA)

    df["bib"] = df["bib"].astype("Int64")
    df["contest_category_id"] = df["contest_category"].str.extract(r"#(\d+)_")[0].astype("Int64")
    df["contest_category"] = df["contest_category"].str.extract(r"_(.*)")[0]
    df["contest_category"] = df["contest_category"].map(get_english_translation)
    df["name"] = df["name"].fillna("").map(string.capwords).replace("", pd.NA)

    gender_mapping = {
        "M": "Male",
        "W": "Female",
        "Männlich": "Male",
        "Weiblich": "Female",
        "Mixed": "Mixed",
    }
    df["gender"] = df["gender"].map(gender_mapping).fillna(df["gender"])

    invalid_clubs = [",  ,", "-", "NONE", "N/A", "KEIN VEREIN"]
    df.loc[df["club"].str.upper().isin(invalid_clubs), "club"] = pd.NA

    df["country"] = df["country"].replace({pd.NA: ""})
    df["country"] = cc.pandas_convert(series=df["country"], src="IOC", to="name_short", not_found=None)
    df["country"] = cc.pandas_convert(series=df["country"], src="ISO3", to="name_short", not_found=None)
    df["country"] = df["country"].replace({"": pd.NA})

    df["year_born"] = pd.to_numeric(df["year_born"], errors="coerce").astype("Int64")
    df["age"] = datetime.datetime.now().year - df["year_born"]

    return df


def process_wait_list_athlete_data(athlete_list_per_category: dict[str, list[str]]) -> pd.DataFrame:
    athlete_rows = [
        [(*athlete, category) for athlete in athletes] for category, athletes in athlete_list_per_category.items()
    ]
    columns = ["autorank", "id", "autorank2", "name", "gender", "age_group", "flag_icon", "country", "contest_category"]
    df = pd.DataFrame(itertools.chain(*athlete_rows), columns=columns)
    df = df.drop(columns="flag_icon")  # .drop(columns="autorank2")

    df = df.replace({None: pd.NA, "": pd.NA})
    df = df.map(lambda v: v.strip() if isinstance(v, str) else v).replace("", pd.NA)

    df["autorank"] = df["autorank"].astype("Int64")
    df["id"] = df["id"].astype("Int64")
    df["autorank2"] = df["autorank2"].astype("Int64")

    df["contest_category_id"] = df["contest_category"].str.extract(r"#(\d+)_")[0].astype("Int64")
    df["contest_category"] = df["contest_category"].str.extract(r"_(.*)")[0]

    df["name"] = df["name"].fillna("").map(string.capwords).replace("", pd.NA)

    gender_mapping = {
        "M": "Male",
        "W": "Female",
        "Männlich": "Male",
        "Weiblich": "Female",
        "Mixed": "Mixed",
    }
    df["gender"] = df["gender"].map(gender_mapping).fillna(df["gender"])

    df["country"] = df["country"].replace({pd.NA: ""})
    df["country"] = cc.pandas_convert(series=df["country"], src="IOC", to="name_short", not_found=None)
    df["country"] = cc.pandas_convert(series=df["country"], src="ISO3", to="name_short", not_found=None)
    df["country"] = df["country"].replace({"": pd.NA})

    return df


def process_splits_data(config_data: ConfigResponse) -> pd.DataFrame:
    col_mapping = {
        "ID": "id",
        "Name": "name",
        "Label": "label",
        "SplitType": "split_type",
        "Contest": "contest_category_id",
        "TypeOfSport": "type_of_sport_id",
    }
    splits_df = pd.DataFrame(config_data["splits"], columns=list(col_mapping.keys()))
    splits_df = splits_df.rename(columns=col_mapping)

    splits_df["label"] = splits_df["label"].map(get_english_translation)
    splits_df["id"] = splits_df["id"].astype("Int64")
    splits_df["split_type"] = splits_df["split_type"].astype("Int64")
    splits_df["contest_category_id"] = splits_df["contest_category_id"].astype("Int64")
    splits_df["type_of_sport_id"] = splits_df["type_of_sport_id"].astype("Int64")

    return splits_df


def get_settings() -> dict[str, str | int]:
    # config = {
    #     "host": "localhost",
    #     "port": 5432,
    #     "dbname": "postgres",
    #     "user": "postgres",
    #     "password": "postgres",
    # }
    # return config

    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=os.environ["SECRET_NAME"])
    secret = json.loads(response["SecretString"])
    return secret


def main():
    config_data, participant_lists = fetch_athlete_data()

    # contests table
    contest_categories_df = pd.DataFrame(config_data["contests"].items(), columns=["id", "name"])
    contest_categories_df["name"] = contest_categories_df["name"].map(get_english_translation)
    contest_categories_df["id"] = contest_categories_df["id"].astype("Int64")

    # splits table
    splits_df = process_splits_data(config_data)

    # athletes table
    athlete_df = process_athlete_data(participant_lists["000-Startlists|Startlist"]["data"])

    # athletes_wait_list table
    wait_list_data = participant_lists.get("000-Startlists|Waitlist")
    athletes_wait_list_df = process_wait_list_athlete_data(wait_list_data["data"]) if wait_list_data else None

    settings = get_settings()
    with create_engine(
        URL.create(
            drivername="postgresql+psycopg",
            username=settings["username"],
            password=settings["password"],
            host=settings["host"].split(":")[0],
            port=settings.get("port") or settings["host"].split(":")[-1],
            database=settings["dbname"],
        )
    ).begin() as connection:
        contest_categories_df.to_sql("contest_categories_df", connection, if_exists="replace", index=False)
        splits_df.to_sql("splits_df", connection, if_exists="replace", index=False)
        athlete_df.to_sql("athletes_df", connection, if_exists="replace", index=False)
        if athletes_wait_list_df is not None:
            athletes_wait_list_df.to_sql("athletes_wait_list_df", connection, if_exists="replace", index=False)

        # audit dataset updates
        row = {
            "created_at": datetime.datetime.now(datetime.UTC),
            "used_data": json.dumps({"config_data": config_data, "participant_lists": participant_lists}),
            "athletes_count": len(athlete_df),
            "athletes_wait_list_count": len(athletes_wait_list_df) if athletes_wait_list_df is not None else 0,
        }
        pd.DataFrame([row]).to_sql("dataset_update_events", connection, if_exists="append", index=False)


if __name__ == "__main__":
    main()


def lambda_handler(event, context):
    main()
