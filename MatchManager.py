import gspread
import aiosqlite
from oauth2client.service_account import ServiceAccountCredentials


class MatchManager:
    def __init__(self, db_path='matches.db', credentials_path='scda-matchbot.json'):
        self.db_path = db_path
        self.credentials_path = credentials_path
        self.gc = None
        self.ultra_key = ""
        self.poke_key = ""
        self.premier_key = ''
        self.test_key = ''
        self.output_key = ''
        self.setup_gspread_client()

    def setup_gspread_client(self):
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, scope)
        self.gc = gspread.authorize(creds)

    async def setup_match_database(self):
        """
        Asynchronously sets up the database for match data.
        This function creates a table for matches if it doesn't exist.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY,
                    week_number INTEGER,
                    team1 TEXT, 
                    team2 TEXT, 
                    score_team1 INTEGER, 
                    score_team2 INTEGER,
                    match_played BOOLEAN DEFAULT 0,
                    replay_url1 TEXT DEFAULT NULL,
                    replay_url2 TEXT DEFAULT NULL,
                    replay_url3 TEXT DEFAULT NULL,
                    division TEXT DEFAULT NULL
                )
            ''')
            await db.commit()
            print("Finished setting up matches database")

    async def insert_matches_into_db(self, matches):
        async with aiosqlite.connect(self.db_path) as db:
            for match in matches:
                await db.execute('''INSERT INTO matches (id, week_number, team1, team2, division)
                                    VALUES (?, ?, ?, ?, ?)''', match)
            await db.commit()

    # Function to extract unique team names
    @staticmethod
    def extract_unique_team_names(sheet):
        """
        Extracts unique team names from a Google Sheet.

        Args:
            sheet: The worksheet object from gspread to read data.

        Returns:
            A list of unique team names, excluding empty values, numeric values,
            and entries that start with 'Week'.
        """
        # Initialize a set to store unique team names
        team_names = set()
        # Iterate through each row in the sheet
        for row in sheet.get_all_values():
            # Filter out empty strings, numeric values, and ignore 'Week' markers
            cleaned_row = [item for item in row if item.strip() not in ['', '0', '1', '2']]
            for name in cleaned_row:
                if name and not name.startswith('Week'):  # Skip week labels or empty cells
                    team_names.add(name.strip())  # Add cleaned team names to the set
        return list(team_names)  # Convert the set to a list to return

    @staticmethod
    def number_of_matches(sheet):
        """
        Counts the number of matches listed in a Google Sheet.

        This function assumes each match is represented by a pair of non-empty,
        non-numeric team names not starting with 'Week'. It counts such pairs
        across all rows to determine the total number of matches.

        Args:
            sheet: The worksheet object from gspread to read data.

        Returns:
            An integer representing the total count of matches.
        """
        all_rows = sheet.get_all_values()
        nr_of_matches = 0

        for row in all_rows:
            # Process the row to identify matches and increase counter
            filtered_row = [item for item in row if item and not item.startswith('Week') and not item.isdigit()]
            for i in range(0, len(filtered_row), 2):
                if i + 1 < len(filtered_row):
                    nr_of_matches += 1
        return nr_of_matches

    def process_matches(self, sheet, unique_team_names, division):
        """
        Processes match data from a Google Sheet and organizes it into a structured list.

        Args:
            sheet: The Google Sheet object containing match data.
            unique_team_names (list): A list of unique team names to determine matches per week.
            division (str): The division identifier for the matches.

        Returns:
            list: A list of lists, each inner list represents a match with the structure:
                  [match_id, current_week, team1, team2, division]

        The function divides rows into odd and even weeks based on their positions in the sheet,
        assuming the format follows a specific pattern. It generates a match ID by concatenating
        the division and team names, then compiles match details accordingly.
        """
        # Fetch all row data from the sheet
        all_rows = sheet.get_all_values()
        # Calculate the number of matches per week based on unique team count
        matches_per_week = len(unique_team_names) / 2

        odd_weeks = []  # Store matches for odd weeks
        even_weeks = []  # Store matches for even weeks

        # Split rows into odd and even weeks based on their position
        for row in all_rows:
            if not row[2].startswith('Week') and row[2]:
                odd_weeks.append(row[:7])
                even_weeks.append(row[7:])

        odd_i = 0
        even_i = 0
        matches = []
        current_week = 1

        # Iterate through the total number of matches
        for i in range(1, self.number_of_matches(sheet)+1):
            if current_week % 2 == 0:  # Process even week matches
                team1 = even_weeks[even_i][2]
                team2 = even_weeks[even_i][5]
                match_id = division + team1 + team2  # Unique match identifier
                match = [match_id, current_week, team1, team2, division]
                matches.append(match)
                even_i += 1
            else:  # Process odd week matches
                team1 = odd_weeks[odd_i][2]
                team2 = odd_weeks[odd_i][5]
                match_id = division + team1 + team2  # Unique match identifier
                match = [match_id, current_week, team1, team2, division]
                matches.append(match)
                odd_i += 1
            if i % matches_per_week == 0 and i != 0:  # Increment week after processing all matches for a week
                current_week += 1

        return matches

    @staticmethod
    def filter_matches(matches):
        weeks = [match[1] for match in matches]
        earliest_week = min(weeks)
        shown_matches = []
        for match in matches:
            if match[1] <= earliest_week+1:
                team1 = "".join([word[0].title() for word in match[2].split()])
                team2 = "".join([word[0].title() for word in match[3].split()])
                shown_matches.append(["W" + str(match[1]) + " " + team1 + " Vs. " + team2, match[0]])
        return shown_matches

    def set_sheet_id_by_division(self, division_name):
        if division_name == "Ultra":
            return self.ultra_key
        elif division_name == "Poke":
            return self.poke_key
        elif division_name == "Premier":
            return self.premier_key
        elif division_name == "Test":
            return self.test_key
        else:
            raise ValueError(f"Unknown division name: {division_name}")

    async def add_matches_for_division(self, division_name):
        sheet_id = self.set_sheet_id_by_division(division_name)
        sheet = self.gc.open_by_key(sheet_id).worksheet("Schedule")  # Open the sheet for the division

        # Extract and process matches
        unique_team_names = self.extract_unique_team_names(sheet)
        matches = self.process_matches(sheet, unique_team_names, division_name)

        # Insert matches into the database
        await self.insert_matches_into_db(matches)

    async def write_matches_to_sheet(self):
        # Open the sheet and select the tab
        sheet = self.gc.open_by_key(self.output_key).worksheet("Matches")

        # Fetch match data from the database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT week_number, team1, team2, score_team1, score_team2, match_played,"
                                      " replay_url1, replay_url2, replay_url3, division FROM matches")
            matches = await cursor.fetchall()

            # Prepare the data for writing, including headers
            data = [["WEEK", "TEAM1", "TEAM2", "SCORE1", "SCORE2", "PLAYED", "REPLAY1", "REPLAY2", "REPLAY3",
                     "DIVISION"]]
            data.extend(matches)

            # Write data to the sheet
            sheet.update('A1', data)

    async def fetch_unplayed_matches(self, division):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, week_number, team1, team2 FROM matches WHERE division = ? AND "
                                      "match_played = 0", (division,))
            matches = await cursor.fetchall()
        return matches

    async def update_match_result(self, match_id, score, urls):
        score_team1, score_team2 = await self.extract_score(score)
        url1, url2, url3 = "", "", ""
        if urls:
            if len(urls) > 0:
                url1 = urls[0]
            if len(urls) > 1:
                url2 = urls[1]
            if len(urls) > 2:
                url3 = urls[2]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE matches SET score_team1=?, score_team2=?, match_played=1, "
                             "replay_url1=?, replay_url2=?, replay_url3=? WHERE id=?",
                             (score_team1, score_team2, url1, url2, url3, match_id))
            await db.commit()
        await self.write_matches_to_sheet()
        pass

    @staticmethod
    async def extract_score(score):
        if score == "2-1":
            return 1, -1
        elif score == "2-0":
            return 2, -2
        elif score == "1-2":
            return -1, 1
        elif score == "0-2":
            return -2, 2
