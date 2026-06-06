import requests
import json


wind_dirs = {
    "N": "северный",
    "NNE": "северо-северо-восточный",
    "NE": "северо-восточный",
    "ENE": "восточно-северо-восточный",
    "E": "восточный",
    "ESE": "восточно-юго-восточный",
    "SE": "юго-восточный",
    "SSE": "юго-юго-восточный",
    "S": "южный",
    "SSW": "юго-юго-западный",
    "SW": "юго-западный",
    "WSW": "западно-юго-западный",
    "W": "западный",
    "WNW": "западно-северо-западный",
    "NW": "северо-западный",
    "NNW": "северо-северо-западный"
}


def get_weather(city):
    url = f"https://wttr.in/{city}?format=j1&lang=ru"

    response = requests.get(url)

    if response.status_code != 200:
        return {
            "error": "Не удалось получить погоду"
        }

    data = response.json()

    current = data["current_condition"][0]
    area = data["nearest_area"][0]

    result = {
        "city": area["areaName"][0]["value"],
        "country": area["country"][0]["value"],
        "region": area["region"][0]["value"],

        "temperature_c": current["temp_C"],
        "feels_like_c": current["FeelsLikeC"],

        "weather": current["lang_ru"][0]["value"],

        "wind_ms": round(int(current["windspeedKmph"]) / 3.6, 1),
        "wind_direction": wind_dirs.get(current["winddir16Point"], current["winddir16Point"]),
    }

    return result


city = input("Введите город: ")

weather = get_weather(city)

print(json.dumps(weather, ensure_ascii=False, indent=4))