import datetime
import unittest
import pandas as pd
import lambda_function


class TestProcessSplitsData(unittest.TestCase):
    def test_process_splits_data(self):
        mock_config_data = {
            "key": "dummy_key",
            "splits": [
                {
                    "ID": 516,
                    "Name": "Start",
                    "Label": "{DE:Eingechecked|EN:Checked-In}",
                    "SplitType": 0,
                    "Contest": 5,
                    "TypeOfSport": 254,
                },
                {
                    "ID": 20,
                    "Name": "Swim",
                    "Label": "{EN:Swim|DE:Schwimmen}",
                    "SplitType": 9,
                    "Contest": 1,
                    "TypeOfSport": 0,
                },
                {
                    "ID": 367,
                    "Name": "Transition1",
                    "Label": "{EN:Transition 1|DE:Wechsel 1}",
                    "SplitType": 9,
                    "Contest": 2,
                    "TypeOfSport": 0,
                },
                {
                    "ID": 4,
                    "Name": "BikeSplit1",
                    "Label": "{DE:Radfahren - Küsnacht, 9,3 km|EN:Bike - Küsnacht, 9.3 km}",
                    "SplitType": 0,
                    "Contest": 1,
                    "TypeOfSport": 11,
                },
                {
                    "ID": 589,
                    "Name": "Spotter",
                    "Label": "{EN:On the finish chute|DE:Auf der Zielgerade}",
                    "SplitType": 0,
                    "Contest": 10,
                    "TypeOfSport": 100,
                },
                {
                    "ID": 452,
                    "Name": "Finish",
                    "Label": "{EN:Finish|DE:Ziel}",
                    "SplitType": 0,
                    "Contest": 3,
                    "TypeOfSport": 100,
                },
            ],
        }

        expected_output = pd.DataFrame(
            {
                "id": pd.Series([516, 20, 367, 4, 589, 452], dtype="Int64"),
                "name": ["Start", "Swim", "Transition1", "BikeSplit1", "Spotter", "Finish"],
                "label": [
                    "Checked-In",
                    "Swim",
                    "Transition 1",
                    "Bike - Küsnacht, 9.3 km",
                    "On the finish chute",
                    "Finish",
                ],
                "split_type": pd.Series([0, 9, 9, 0, 0, 0], dtype="Int64"),
                "contest_category_id": pd.Series([5, 1, 2, 1, 10, 3], dtype="Int64"),
                "type_of_sport_id": pd.Series([254, 0, 0, 11, 100, 100], dtype="Int64"),
            }
        )

        output_df = lambda_function.process_splits_data(mock_config_data)
        pd.testing.assert_frame_equal(output_df.reset_index(drop=True), expected_output.reset_index(drop=True))

    def test_get_english_translation(self):
        cases = [
            ("{DE:Eingechecked|EN:Checked-In}", "Checked-In"),
            ("{EN:Checked-In|DE:Eingechecked}", "Checked-In"),
            ("{PT:Registo|EN:Checked-In|DE:Eingechecked}", "Checked-In"),
            ("{DE:Eingechecked}", "{DE:Eingechecked}"),
        ]
        for label, expected in cases:
            with self.subTest(label=label, expected=expected):
                self.assertEqual(lambda_function.get_english_translation(label), expected)

    def test_process_athlete_data(self):
        # Mock athlete data structured as in the example
        mock_athlete_data = {
            "#1_Olympisch": [
                [
                    "1660",
                    "",
                    "Felipe ABELLA",
                    "M",
                    "",
                    "M20-34",
                    "",
                    "",
                    "[img:https://timit.ch/graphics/flags/ch_black.png|height:16px;width:20px;]",
                    "SUI",
                    "1993",
                ],
                [
                    "1697",
                    "",
                    "Markus ACKERMANN",
                    "M",
                    "",
                    "M55-64",
                    "Blaue Funken Köln",
                    "",
                    "[img:https://timit.ch/graphics/flags/de_black.png|height:16px;width:20px;]",
                    "GER",
                    "1968",
                ],
                [
                    "1954",
                    "",
                    "Seline ACKERMANN",
                    "W",
                    "",
                    "W20-34",
                    "Schweiz",
                    "",
                    "[img:https://timit.ch/graphics/flags/ch_black.png|height:16px;width:20px;]",
                    "SUI",
                    "1993",
                ],
            ],
            "#5_Jugendtriathlon U14": [
                [
                    "278",
                    "",
                    "Théophile ANIOL",
                    "M",
                    "",
                    "M12-13",
                    "",
                    "Company",
                    "[img:https://timit.ch/graphics/flags/fr_black.png|height:16px;width:20px;]",
                    "FRA",
                    "2013",
                ],
                [
                    "249",
                    "",
                    "Eleonora BECK",
                    "W",
                    "",
                    "W10-11",
                    "",
                    "",
                    "[img:https://timit.ch/graphics/flags/ch_black.png|height:16px;width:20px;]",
                    "SUI",
                    "2014",
                ],
            ],
        }

        # Expected output DataFrame
        current_year = datetime.datetime.now().year
        expected_output = pd.DataFrame(
            {
                "bib": pd.Series([1660, 1697, 1954, 278, 249], dtype="Int64"),
                "contest": pd.Series([pd.NA, pd.NA, pd.NA, pd.NA, pd.NA]),
                "name": ["Felipe Abella", "Markus Ackermann", "Seline Ackermann", "Théophile Aniol", "Eleonora Beck"],
                "gender": ["Male", "Male", "Female", "Male", "Female"],
                "start": pd.Series([pd.NA, pd.NA, pd.NA, pd.NA, pd.NA]),
                "age_group": ["M20-34", "M55-64", "W20-34", "M12-13", "W10-11"],
                "club": pd.Series([pd.NA, "Blaue Funken Köln", "Schweiz", pd.NA, pd.NA]),
                "company": pd.Series([pd.NA, pd.NA, pd.NA, "Company", pd.NA]),
                "country": ["Switzerland", "Germany", "Switzerland", "France", "Switzerland"],
                "year_born": pd.Series([1993, 1968, 1993, 2013, 2014], dtype="Int64"),
                "contest_category": [
                    "Olympisch",
                    "Olympisch",
                    "Olympisch",
                    "Jugendtriathlon U14",
                    "Jugendtriathlon U14",
                ],
                "contest_category_id": pd.Series([1, 1, 1, 5, 5], dtype="Int64"),
                "age": pd.Series(
                    [
                        current_year - 1993,
                        current_year - 1968,
                        current_year - 1993,
                        current_year - 2013,
                        current_year - 2014,
                    ],
                    dtype="Int64",
                ),
            }
        )

        output_df = lambda_function.process_athlete_data(mock_athlete_data)
        pd.testing.assert_frame_equal(output_df.reset_index(drop=True), expected_output.reset_index(drop=True))

    def test_process_wait_list_athlete_data(self):
        mock_waitlist_data = {
            "#1_Olympisch - Warteliste": [
                [
                    "20180",
                    "1",
                    "20180",
                    "Maximilian HOHL",
                    "M",
                    "",
                    "[img:https://timit.ch/graphics/flags/at_black.png|height:16px;width:20px;]",
                    "XKX",
                ],
                [
                    "20200",
                    "21",
                    "20200",
                    "Katha SCHULER",
                    "W",
                    "",
                    "[img:https://timit.ch/graphics/flags/de_black.png|height:16px;width:20px;]",
                    "GER",
                ],
                [
                    "20211",
                    "32",
                    "20211",
                    "Cédric SCHÜTZ",
                    "M",
                    "",
                    "[img:https://timit.ch/graphics/flags/ch_black.png|height:16px;width:20px;]",
                    "UMI",
                ],
            ]
        }

        expected_output = pd.DataFrame(
            {
                "autorank": pd.Series([20180, 20200, 20211], dtype="Int64"),
                "id": pd.Series([1, 21, 32], dtype="Int64"),
                "autorank2": pd.Series([20180, 20200, 20211], dtype="Int64"),
                "name": ["Maximilian Hohl", "Katha Schuler", "Cédric Schütz"],
                "gender": ["Male", "Female", "Male"],
                "age_group": pd.Series([pd.NA, pd.NA, pd.NA]),
                "country": ["Kosovo", "Germany", "United States Minor Outlying Islands"],
                "contest_category": ["Olympisch - Warteliste", "Olympisch - Warteliste", "Olympisch - Warteliste"],
                "contest_category_id": pd.Series([1, 1, 1], dtype="Int64"),
            }
        )

        output_df = lambda_function.process_wait_list_athlete_data(mock_waitlist_data)

        pd.testing.assert_frame_equal(output_df.reset_index(drop=True), expected_output.reset_index(drop=True))


if __name__ == "__main__":
    unittest.main()
