"""Script to pull Form 8-K filings from the SEC site and index on GitHub."""

import os
import re
from datetime import datetime
import logging
import base64

from bs4 import BeautifulSoup
import requests

TESTING = False

ITEM = "5.02" if TESTING else "1.05"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    raise ValueError(
        "GitHub token not found. Set the GITHUB_TOKEN env variable."
    )
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

logging.basicConfig(level=logging.INFO)


def get_sec_url(index):
    """Return the relevant items on the SEC's 'latest filings' page"""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&datea=&dateb=&company=&type=8-k&SIC=&State=&Country=&CIK=&owner="
        f"include&accno=&start={index}&count=100"
    )


def update_github_file(entries_to_file, current_sha=None):
    """Update the GitHub file with the latest Form 8-K entries."""
    logging.info("Updating %s with filings.", FILE_PATH)
    full_content = HEADING
    full_content += entries_to_file if entries_to_file else ''

    message = f"Update {FILE_PATH}" if current_sha else f"Create {FILE_PATH}"
    payload = {
        "message": message,
        "content": base64.b64encode(full_content.encode()).decode('utf-8'),
        "sha": current_sha.strip('"') if current_sha else None
    }

    response = requests.put(
        GITHUB_API_URL, headers=GITHUB_HEADERS, json=payload, timeout=10
    )

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


def get_filing_info(element):
    """Extract information from Form 8-K filing HTML element."""
    soup = BeautifulSoup(str(element[0]), 'html.parser')

    company = soup.find('a').get_text()
    company = re.sub(r'\([^)]*\) \(Filer\)\s*', '', company).strip()

    soup = BeautifulSoup(str(element[1]), 'html.parser')

    date_time = (
        soup.find(
            lambda tag: tag.name == 'td' and tag.find('br'),
            {'nowrap': 'nowrap'}
        )
        .get_text()
    )
    date_time_obj = datetime.strptime(date_time, '%Y-%m-%d%H:%M:%S')
    date_time = date_time_obj.strftime("%Y-%m-%d %H:%M:%S")

    html_link = soup.find('a', string='[html]')
    full_url = f"[link](https://www.sec.gov{html_link.get('href')})"

    return f"|{company}|{date_time}|{full_url}|\n"


def get_8ks():
    """Retrieve Form 8-K filings from the SEC's 'latest filings' page."""
    logging.info("ACcessing the SEC 'latest filings' page.")
    getting_data = True
    index = 0
    relevant_filings = ''

    while getting_data:
        current_url = get_sec_url(index)
        logging.info("Checking 'latest filings' page %s.", int(index/100)+1)

        with requests.Session() as session:
            response = session.get(current_url, headers=SEC_HEADERS)

        # Check if the request was successful
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

        # Check if we're on the last available page
        if entries_on_current_page < 100:
            getting_data = False
        else:
            index += 100

        # Iterate through each <tr> element
        for tr_element in tr_elements_with_item:
            relevant_filings += get_filing_info(tr_element)

    return relevant_filings


def get_exisiting_entries():
    """Retrieve existing Form 8-K entries from the GitHub repo."""
    logging.info("Retrieving any existing data from %s.", FILE_PATH)
    try:
        response = requests.get(
            GITHUB_API_URL, headers=GITHUB_HEADERS, timeout=10
        )

        if response.status_code == 200:
            current_sha = response.headers.get('ETag')
            current_content = response.text.replace('\r', '')
            current_content_as_strings = current_content.splitlines()
            bottom_half = current_content_as_strings[5:]
            logging.info("Extracted existing data from %s.", FILE_PATH)
            return bottom_half, current_sha

        logging.info("%s doesn't exist", FILE_PATH)
        return None

    except requests.exceptions.RequestException as exception:
        logging.error(
            "An error occurred during the request: %s", str(exception)
        )
        return None


def combine_lists(new_entries, old_entries):
    """Combine new filings with existing filings"""
    # Extract timestamps from the lists
    final_list = []
    cutoff_timestamp = old_entries[0].split('|')[2]

    for entry in new_entries:
        if entry.split('|')[2] > cutoff_timestamp:
            final_list.append(entry)
        else:
            break
    final_list += old_entries
    return final_list


def tuple_to_string(entries_tuple):
    """Convert tuple to string."""
    new_content = ''
    for row in entries_tuple:
        new_content += f"{'|'.join(str(cell) for cell in row)}\n"
    return new_content


def main():
    """Main function to check and update Form 8-K entries on GitHub."""

    # Get new filings
    new_entries_single_string = get_8ks()
    new_entries_list = new_entries_single_string.splitlines()

    # Get existing filings
    existing_entries_list, current_sha = get_exisiting_entries()

    # Create a final list of filings (combining old and new if needed)
    logging.info("Creating final list of entries.")
    if existing_entries_list:
        updated_string_of_entries = '\n'.join(
            combine_lists(new_entries_list, existing_entries_list)
        )
    else:
        updated_string_of_entries = '\n'.join(new_entries_list)

    # Update the file with the final list of filings
    update_github_file(updated_string_of_entries, current_sha or '')


if __name__ == "__main__":
    main()
