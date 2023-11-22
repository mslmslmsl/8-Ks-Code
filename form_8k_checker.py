"""Script to pull Form 8-K filings from the SEC site and index on GitHub."""

import os
import re
from datetime import datetime
import logging
import base64

from bs4 import BeautifulSoup
import requests

# Constants
TESTING = False
ITEM = "5.02" if TESTING else "1.05"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    raise ValueError("GitHub token not found. Set the GITHUB_TOKEN env var.")
REPO_OWNER = "mslmslmsl"
REPO_NAME = "TEST" if TESTING else "8-Ks"
FILE_PATH = "8-Ks.md"
GITHUB_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/"
    f"{REPO_NAME}/contents/{FILE_PATH}"
)
HEADING = (
    f"# List of Form 8-Ks with item {ITEM}\n"
    f"Last checked {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    "|Company|Timestamp|Link|\n"
    "|---|---|---|\n"
)
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.raw",
}
SEC_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    )
}

# Show me the logs
logging.basicConfig(level=logging.INFO)


def get_sec_url(index: int) -> str:
    """Return the URL for the relevant page of the 'latest filings' site"""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&datea=&dateb=&company=&type=8-k&SIC=&State=&Country=&CIK=&owner="
        f"include&accno=&start={index}&count=100"
    )


def update_github_file(entries_to_file: str, current_sha: str) -> None:
    """Update the GitHub file with the latest Form 8-K entries."""
    logging.info("Updating %s with filings.", FILE_PATH)

    # Set the content of the file to HEADING plus the entries
    full_content = HEADING
    full_content += entries_to_file if entries_to_file else ''

    # Upload to GitHub
    message = f"Update {FILE_PATH}" if current_sha else f"Create {FILE_PATH}"
    payload = {
        "message": message,
        "content": base64.b64encode(full_content.encode()).decode('utf-8'),
        "sha": current_sha.strip('"') if current_sha else None
    }
    response = requests.put(
        GITHUB_API_URL, headers=GITHUB_HEADERS, json=payload, timeout=10
    )

    # Log the response
    if response.status_code == 200:
        logging.info("Updated %s successfully.", FILE_PATH)
    elif response.status_code == 201:
        logging.info("Created %s successfully.", FILE_PATH)
    else:
        logging.error(
            "Error interacting with %s. HTTP Status Code: %s, Response: %s",
            FILE_PATH,
            response.status_code,
            response.text
        )


def get_filing_info(element: tuple) -> str:
    """Extract information from Form 8-K filing HTML element."""
    soup = BeautifulSoup(str(element[0]), 'html.parser')

    # Get the company name (assume that an <a> tag always exists in element[0])
    company = soup.find('a').get_text()
    company = re.sub(r'\([^)]*\) \(Filer\)\s*', '', company).strip()

    soup = BeautifulSoup(str(element[1]), 'html.parser')

    # Get the timestamp (and assume that a <td> tag with a <br> tag always
    # exists in element[1])
    date_time = (
        soup.find(
            lambda tag: tag.name == 'td' and tag.find('br'),
            {'nowrap': 'nowrap'}
        )
        .get_text()
    )
    date_time_obj = datetime.strptime(date_time, '%Y-%m-%d%H:%M:%S')
    date_time = date_time_obj.strftime("%Y-%m-%d %H:%M:%S")

    # Get the URL to the actual form filing
    html_link = soup.find('a', string='[html]')
    full_url = f"[link](https://www.sec.gov{html_link.get('href')})"

    # Return a string with the data
    return f"|{company}|{date_time}|{full_url}|\n"


def get_8ks() -> str:
    """Retrieve Form 8-K filings from the SEC's 'latest filings' page."""
    logging.info("Accessing the SEC 'latest filings' page.")

    getting_data = True
    index = 0
    relevant_filings = ''

    # Loop through each page of the SEC 'latest filings' site
    while getting_data:

        # Request the page
        logging.info("Checking 'latest filings' page %s.", int(index/100)+1)
        current_url = get_sec_url(index)
        with requests.Session() as session:
            response = session.get(current_url, headers=SEC_HEADERS)

        # If the page doesn't load, throw an error and return
        if response.status_code != 200:
            logging.error(
                "Failed to load SEC data (code: %s) for URL: %s",
                response.status_code,
                current_url
            )
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all <tr> elements
        tr_elements = soup.find_all('tr')

        # If we find the item, save the row and the prior one
        entries_on_current_page = 0
        tr_elements_with_item = []
        for prev_tr, current_tr in zip(tr_elements, tr_elements[1:]):
            text = current_tr.get_text()
            if "Current report" in text:
                entries_on_current_page += 1
                if ITEM in text:
                    tr_elements_with_item.append((prev_tr, current_tr))

        # Break out of the loop if we're on the last page (i.e., <100 entries)
        if entries_on_current_page < 100:
            getting_data = False
        else:
            index += 100

        # For each entry saved, get the relevant info (name, timestamp, link)
        for tr_element in tr_elements_with_item:
            relevant_filings += get_filing_info(tr_element)

    return relevant_filings


def get_exisiting_entries() -> tuple:
    """Retrieve existing Form 8-K entries from the GitHub repo."""
    logging.info("Retrieving any existing data from %s.", FILE_PATH)

    # Pull data from GitHub
    try:
        response = requests.get(
            GITHUB_API_URL, headers=GITHUB_HEADERS, timeout=10
        )

        # If we succeed, then process the existing entries
        if response.status_code == 200:

            # Get the sha of the response (which has to be sent back)
            current_sha = response.headers.get('ETag')

            # Get lines from the file and create a list of strings
            current_content = response.text.replace('\r', '')
            current_content_as_strings = current_content.splitlines()

            # Isolate the form 8-K lines
            bottom_half = current_content_as_strings[5:]

            logging.info("Extracted existing data from %s.", FILE_PATH)
            return bottom_half, current_sha

        logging.info("%s doesn't exist", FILE_PATH)
        return None, None

    except requests.exceptions.RequestException as exception:
        logging.error(
            "An error occurred during the request: %s", str(exception)
        )
        return None, None


def combine_lists(new_entries: list, old_entries: list) -> list:
    """Combine the list of new filings with the list of existing filings"""

    # Define variable to store the final list of filings
    final_list = []

    # Get the timestamp for the most recent existing entry
    cutoff_timestamp = old_entries[0].split('|')[2]

    # Include all new entries if later than the most recent existing entry
    for entry in new_entries:
        if entry.split('|')[2] > cutoff_timestamp:
            final_list.append(entry)
        else:
            break

    # Finally, add all the old entries to the list
    final_list += old_entries

    # Return the full list of entries to be saved
    return final_list


def main():
    """Main function to check and update the Form 8-K entries on GitHub."""

    # Get new filings as a string
    new_entries_string = get_8ks()

    # Turn the new entries into a list of strings (one filing per string)
    new_entries_list = new_entries_string.splitlines()

    # Get existing filings as a list of strings (one filing per string)
    existing_entries_list, current_sha = get_exisiting_entries()

    # Here, do two things: (1) get a final list of filings that need to be
    # stored on GitHub; and (2) turn the list back into a giant string (filings
    # separated with newlines)
    logging.info("Creating final list of entries.")
    if existing_entries_list:
        all_entries_string = '\n'.join(
            combine_lists(new_entries_list, existing_entries_list)
        )
    else:
        all_entries_string = '\n'.join(new_entries_list)

    # Finally, update the file with the string of all filings
    # If `current_sha` exists, we are modifying the file (not creating it)
    update_github_file(all_entries_string, current_sha or '')


if __name__ == "__main__":
    main()
