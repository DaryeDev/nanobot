import sys
import requests

def get_weather(city):
    # We use format 3 or a custom format for a clean one-liner
    # %l: location, %c: condition, %t: temperature, %h: humidity, %w: wind
    url = f"https://wttr.in/{city.replace(' ', '+')}?format=%l:+%c+%t+%h+%w"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(response.text.strip())
    except Exception as e:
        print(f"Error fetching weather for {city}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python weather.py <city_name>")
        sys.exit(1)
    
    city_name = " ".join(sys.argv[1:])
    get_weather(city_name)
