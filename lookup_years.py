import requests

def extract_years():
    """Extract release years from iTunes for each track ID in songs.txt and write to years.txt"""

    # Read track IDs from songs.txt
    with open('songs.txt', 'r') as f:
        track_ids = [line.strip() for line in f if line.strip()]

    count = 0

    # Open years.txt for writing - writes each year immediately
    with open('years.txt', 'w') as year_file:
        for track_id in track_ids:
            count += 1
            print(f"Processing {count}/{len(track_ids)}: ID {track_id}")

            try:
                # Try NL region first
                url = f"https://itunes.apple.com/nl/lookup?id={track_id}"
                response = requests.get(url)
                response.raise_for_status()
                res = response.json()['results']

                # If not found in NL, try US region
                if not res:
                    url = f"https://itunes.apple.com/us/lookup?id={track_id}"
                    response = requests.get(url)
                    response.raise_for_status()
                    res = response.json()['results']

                if res:
                    data = res[0]
                    # Extract year from releaseDate (format: "2023-01-15T12:00:00Z")
                    release_date = data.get('releaseDate', '')
                    year = release_date[:4] if release_date else 'Unknown'
                    year_file.write(year + '\n')
                    year_file.flush()  # Force write to disk immediately
                    print(f"  -> {data.get('artistName', 'Unknown')} - {data.get('trackName', 'Unknown')} ({year})")
                else:
                    year_file.write('Unknown\n')
                    year_file.flush()
                    print(f"  -> Not found")

            except Exception as e:
                print(f"  -> ERROR: {e}")
                year_file.write('Unknown\n')
                year_file.flush()

    print(f"\nDone! Wrote {count} years to years.txt")

if __name__ == '__main__':
    extract_years()
