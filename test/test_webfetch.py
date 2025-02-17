import pytest
import requests
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock
from cfmb.webfetch import get_webpage_text, extract_first_url  # Replace your_module

# Sample HTML content for testing
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>This is a test paragraph.</p>
    <div>Some <span>text in a div</span>.</div>
    <p>Another paragraph.</p>
</body>
</html>
"""

# --- Tests for get_webpage_text ---


@patch("requests.get")
def test_get_webpage_text_success(mock_get):
    """Test successful retrieval and parsing of webpage text."""
    mock_response = MagicMock()
    mock_response.content = SAMPLE_HTML
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    url = "http://example.com"
    result = get_webpage_text(url)

    assert result is not None
    assert "Welcome" in result
    assert "This is a test paragraph." in result
    assert "Some" in result
    assert "text in a div" in result
    assert "Another paragraph." in result
    assert "\n\n" not in result
    mock_get.assert_called_once_with(url)


@patch("requests.get")
def test_get_webpage_text_request_exception(mock_get):
    """Test handling of RequestException (e.g., network error)."""
    mock_get.side_effect = requests.exceptions.RequestException("Network error")
    url = "http://example.com"
    result = get_webpage_text(url)
    assert result is None
    mock_get.assert_called_once_with(url)


@patch("requests.get")
def test_get_webpage_text_http_error(mock_get):
    """Test handling of HTTP errors (e.g., 404, 500)."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "404 Error"
    )
    mock_get.return_value = mock_response

    url = "http://example.com/404"
    result = get_webpage_text(url)
    assert result is None
    mock_get.assert_called_once_with(url)


@patch("requests.get")
def test_get_webpage_text_parsing_error(mock_get):
    """Test handling of unexpected HTML structure."""
    mock_response = MagicMock()
    mock_response.content = "This is not valid HTML"
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    url = "http://example.com/invalid"
    result = get_webpage_text(url)
    assert result is not None
    mock_get.assert_called_once_with(url)


@patch("requests.get")
def test_get_webpage_text_empty_content(mock_get):
    """Test handling of a webpage with empty content."""
    mock_response = MagicMock()
    mock_response.content = ""
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    url = "http://example.com/empty"
    result = get_webpage_text(url)
    assert result == ""
    mock_get.assert_called_once_with(url)


# --- Tests for extract_first_url ---


def test_extract_first_url_valid():
    """Test extraction of a valid URL."""
    text = "Visit my website at https://www.example.com/page1"
    expected_url = "https://www.example.com/page1"
    assert extract_first_url(text) == expected_url

    text = "Visit my website at http://www.example.com/page1"
    expected_url = "http://www.example.com/page1"
    assert extract_first_url(text) == expected_url


def test_extract_first_url_no_url():
    """Test case where no URL is present."""
    text = "This is a string with no URL."
    assert extract_first_url(text) is None


def test_extract_first_url_with_path_and_query():
    """Test a URL with a path and query parameters."""
    text = "Check this out: https://www.example.com/path/to/resource?param1=value1&param2=value2"
    expected_url = (
        "https://www.example.com/path/to/resource?param1=value1&param2=value2"
    )
    assert extract_first_url(text) == expected_url


def test_extract_first_url_url_at_beginning():
    """Test a URL at the very beginning of the string."""
    text = "https://www.example.com is the website."
    expected_url = "https://www.example.com"
    assert extract_first_url(text) == expected_url


def test_extract_first_url_multiple_urls():
    """Test with multiple URLs, ensuring only the first is returned."""
    text = "First URL: https://www.first.com, Second URL: https://www.second.com"
    expected_url = "https://www.first.com"
    assert extract_first_url(text) == expected_url


def test_extract_first_url_no_www():
    """Test a valid URL that may not contain www"""
    text = "Visit my website at https://example.com/page1"
    expected_url = "https://example.com/page1"
    assert extract_first_url(text) == expected_url


def test_extract_first_url_long_url():
    """Test a valid URL that is very long"""
    text = "Visit my website at https://example.com/page1/page2/page3/page4/page5/page6/page7/page8/page9/page10/page11/page12/page13/page14/page15"
    expected_url = "https://example.com/page1/page2/page3/page4/page5/page6/page7/page8/page9/page10/page11/page12/page13/page14/page15"
    assert extract_first_url(text) == expected_url


def test_extract_first_url_empty_string():
    """Test an empty string as input."""
    text = ""
    assert extract_first_url(text) is None
