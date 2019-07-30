import csv
import math
import requests


API_KEY = ''
ZOOM_NUMBER = 18  # building
LAT_DEGREE_METERS = 111300

EXCLUDE_TYPES = ('industrial', 'forest', 'water', 'highway', 'railway')
REQUIRED_FILEDS = ('City', 'Number')


assert API_KEY, 'google maps api key is required'


def add_lat_metters(lat, metters):
    """add south coords"""
    return lat - (metters / LAT_DEGREE_METERS)


def add_lon_metters(lon, lat, metters):
    """add east coords"""
    lon_degree_meters = LAT_DEGREE_METERS * math.cos(lat)
    return lon - (metters / lon_degree_meters)


def cmp_less_than_max(min_curr_val, max_cur_val, min_value, max_value):
    if max_value > min_value:
        return min_curr_val < max_cur_val
    return min_curr_val > max_cur_val


add_metters_func = {
    'lat': add_lat_metters,
    'lon': add_lon_metters,
}


def generate_steps(name, min_val, max_val, distance, current_lat=None):
    steps = []
    current_step = min_val
    while cmp_less_than_max(current_step, max_val, min_val, max_val):
        steps.append(current_step)
        options = {
            name: current_step,
            'metters': distance,
        }
        if current_lat is not None:
            options['lat'] = current_lat
        new_current_step = add_metters_func[name](**options)

        if not cmp_less_than_max(current_step, new_current_step, min_val, max_val):
            current_step += current_step - new_current_step
        else:
            current_step = new_current_step

    return steps


def fetch_addresses_by_zip(zip_code, distance, country='DE'):
    addresses = []

    get_bbox_url = 'https://maps.googleapis.com/maps/api/geocode/json' \
                  f'?components=postal_code:{zip_code}|country:{country}&key={API_KEY}'
    bbox_data = requests.get(get_bbox_url).json()
    if not bbox_data.get('results'):
        raise ValueError(
            f'Failed to find bbox data for zip_code={zip_code} and country={country}, bbox_data={bbox_data}'
        )

    # {'northeast': {'lat': 52.553013, 'lng': 13.426989}, 'southwest': {'lat': 52.53932, 'lng': 13.3988029}}
    bbox = bbox_data['results'][0]['geometry']['bounds']
    min_lat = bbox['northeast']['lat']
    min_lon = bbox['southwest']['lng']
    max_lat = bbox['southwest']['lat']
    max_lon = bbox['northeast']['lng']

    lat_steps = generate_steps('lat', min_lat, max_lat, distance)
    # we can't generate lon_steps before the loop as well as lat_steps,
    # because lon value depends on a current lat value
    for current_lat in lat_steps:
        lon_steps = generate_steps('lon', min_lon, max_lon, distance, current_lat=current_lat)
        for current_lon in lon_steps:
            nominatim_reverse_url = 'https://nominatim.openstreetmap.org/reverse' \
                                   f'?lat={current_lat}&lon={current_lon}&zoom={ZOOM_NUMBER}&format=geojson'
            reverse_geocoding_data = requests.get(nominatim_reverse_url).json()
            for feature in reverse_geocoding_data['features']:
                properties = feature['properties']
                address = properties.get('address', {})
                address_type = properties.get('type', '')

                if not address_type:
                    print(f'Failed to find `type` in properties={properties}')

                if str(address.get('postcode', '')) != str(zip_code):
                    print(f'skip(postcode does not match) {address}')
                    continue

                address.update({
                    '_type': address_type,
                    '_latitude': str(current_lat),
                    '_longitude': str(current_lon),
                    '_included': int(address_type not in EXCLUDE_TYPES),
                })

                if address not in addresses:
                    addresses.append(address)

    return addresses


def save_addresses_by_zipcodes(zip_codes, distance, country='DE', file_path='result.csv'):
    fieldnames = ['ZipCode', 'City', 'Street', 'Number', 'Type', 'Latitude', 'Longitude', 'Included']

    with open(file_path, mode='w') as csv_file:
        # write unquoted headers
        writer = csv.writer(csv_file)
        writer.writerow(fieldnames)

        # write data
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC, quotechar="'")  
        for zip_code in zip_codes:
            addresses = fetch_addresses_by_zip(zip_code, distance, country)
            for address in addresses:
                data = {
                    'ZipCode': address.get('postcode', ''),
                    'City': address.get('city', '') or address.get('town', '') or address.get('city_district', ''),
                    'Street': address.get('road', ''),
                    'Number': address.get('house_number', ''),
                    'Type': address['_type'],
                    'Latitude': address['_latitude'],
                    'Longitude': address['_longitude'],
                    'Included': address['_included'],
                }
                skip = False
                for required_field in REQUIRED_FILEDS:
                    if not data.get(required_field):
                        skip = True
                        break
                if not skip:
                    writer.writerow(data)
