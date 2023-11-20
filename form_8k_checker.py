"""Script to pull Form 8-K filings from the SEC site and index on GitHub."""

import os
import re
from datetime import datetime
import logging
import base64

from bs4 import BeautifulSoup
import requests

ITEM = "1.05"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    raise ValueError(
        "GitHub token not found. Set the GITHUB_TOKEN env variable."
    )
REPO_OWNER = "mslmslmsl"
REPO_NAME = "8-Ks"
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

    return ('', company, date_time, full_url, '')


def get_8ks():
    """Retrieve Form 8-K filings from the SEC's 'latest filings' page."""
    getting_data = True
    index = 0
    form_8ks_with_item = []

    while getting_data:
        current_url = get_sec_url(index)
        logging.info("Checking page %s", int(index/100)+1)

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
            form_8ks_with_item.append(get_filing_info(tr_element))

    return form_8ks_with_item


def get_exisiting_entries():
    """Retrieve existing Form 8-K entries from the GitHub repo."""
    try:
        response = requests.get(
            GITHUB_API_URL, headers=GITHUB_HEADERS, timeout=10
        )

        if response.status_code == 200:
            current_sha = response.headers.get('ETag')
            current_content = response.text.replace('\r', '')

            # Parse the current content into a list of lists
            rows = [
                tuple(row.split("|"))
                for row in current_content.strip().split("\n")
            ]

            # Get just the table entries
            bottom_half = rows[5:]

            logging.info("Extracted existing data from %s", FILE_PATH)
            return bottom_half, current_sha

        logging.info("%s doesn't exist", FILE_PATH)
        return None

    except requests.exceptions.RequestException as exception:
        logging.error(
            "An error occurred during the request: %s", str(exception)
        )
        return None


def filter_new_entries(new_list, old_list):
    """Combine new and existing 8-K entries."""
    # Keep only new items that are newer than the most recent item in old
    new_items = [item for item in new_list if item[2] > old_list[0][2]]

    # Combine new_items with old to preserve order
    items_to_save = new_items + old_list

    return items_to_save


def tuple_to_string(entries_tuple):
    """Convert tuple to string."""
    new_content = ''
    for row in entries_tuple:
        new_content += f"{'|'.join(str(cell) for cell in row)}\n"
    return new_content


def main():
    """Main function to check and update Form 8-K entries on GitHub."""
    current_sha = ''
    new_entries = get_8ks()
    existing_entries = []
    existing_entries_result = get_exisiting_entries()
    if existing_entries_result:
        existing_entries, current_sha = existing_entries_result

    entries_to_save_tuple = (
        filter_new_entries(new_entries, existing_entries)
        if new_entries and existing_entries
        else new_entries or existing_entries or []
    )

    entries_to_save_string = tuple_to_string(entries_to_save_tuple)

    update_github_file(entries_to_save_string, current_sha)


if __name__ == "__main__":
    main()
