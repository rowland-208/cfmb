import re

import requests
from bs4 import BeautifulSoup


def get_webpage_text(url: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        soup = BeautifulSoup(response.content, "html.parser")

        # Method 1: Get all text, then clean up whitespace and join
        all_text = soup.get_text(
            separator="\n"
        )  # Use newline as separator to preserve some structure
        cleaned_text = "\n".join(
            line.strip() for line in all_text.splitlines() if line.strip()
        )  # Remove empty lines
        return cleaned_text

        # Method 2 (more targeted and sometimes cleaner): Extract from specific tags
        # If you know the relevant content is within certain tags (e.g., <p>, <div>, etc.)
        # you can target them for potentially better results.
        # Example:
        # text_parts = []
        # for element in soup.find_all(["p", "div", "span"]): # Example tags - adjust as needed
        #     text = element.get_text(separator='\n').strip()
        #     if text:  # Avoid adding empty strings
        #         text_parts.append(text)
        # return "\n".join(text_parts)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def extract_first_url(text):
    """
    Extracts the first URL from a string.

    Args:
        text: The input string.

    Returns:
        The first URL found in the string, or None if no URL is found.
    """
    url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
    match = re.search(url_pattern, text)  # Use re.search to find the first match

    if match:
        return match.group(0)  # Return the matched URL
    else:
        return None
