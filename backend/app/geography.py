import json
from urllib.parse import urlencode
from urllib.request import urlopen


class GeographyLookupError(Exception):
    pass


STATE_FIPS_TO_CODE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE",
    "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA",
    "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM",
    "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}


def lookup_us_geography(latitude: float, longitude: float) -> tuple[str, str]:
    """Return a U.S. state code and county derived from Census coordinates."""
    query = urlencode(
        {
            "x": longitude,
            "y": latitude,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        }
    )
    try:
        with urlopen(f"https://geocoding.geo.census.gov/geocoder/geographies/coordinates?{query}", timeout=5) as response:
            payload = json.load(response)
        counties = payload["result"]["geographies"]["Counties"]
        county = counties[0]
        state_code = STATE_FIPS_TO_CODE[county["STATE"]]
        return state_code, county["NAME"]
    except (KeyError, IndexError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise GeographyLookupError("We could not verify that location as a U.S. address.") from exc
