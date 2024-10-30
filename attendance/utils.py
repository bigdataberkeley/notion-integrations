import requests
import datetime

from keys import NOTION_SECRET, EVENTS_DATABASE_ID, ATTENDANCE_TRACKER_DATABASE_ID

headers = {
    "Authorization": "Bearer " + NOTION_SECRET,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

person_to_attendance_sheet = dict()     # dict[person_id -> Page]
person_to_attendance_table = dict()     # dict[person_id -> Block]
person_id_to_user = dict()              # dict[person_id -> User]
event_id_to_event = dict()              # dict[event_id -> Page]

ignored_users = set([
        "Ria Jain",
        "Cadence Hsu",
        "Priya Kamath",
        "Sean She",
        "Amrutha Srivatsav",
        "Neha Rachapudi",
        "Ronit Nagarapu (Personal)",
        "Big Data at Berkeley",
        "Data Extractor",
        "Attendance Tracker",
        "Resume Manager",
    ])


def get_pages(database_id, num_pages=None):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"

    get_all = num_pages is None
    page_size = 100 if get_all else num_pages

    payload = {"page_size": page_size}
    response = requests.post(url, json=payload, headers=headers)

    data = response.json()

    if data['object'] == 'error':
        raise ValueError(f'Could not get pages from database {database_id}')

    results = data["results"]
    while data["has_more"] and get_all:
        payload = {"page_size": page_size, "start_cursor": data["next_cursor"]}
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        results.extend(data["results"])

    return results


def get_all_users():
    url = f"https://api.notion.com/v1/users"
    payload = {}
    response = requests.get(url, json=payload, headers=headers)

    data = response.json()

    if data['object'] == 'error':
        raise ValueError('Could not get users from Notion Workspace')

    results = data["results"]
    while data["has_more"]:
        payload = {"start_cursor": data["next_cursor"]}
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        results.extend(data["results"])

    return results


def get_person(person_id):
    if person_id in person_id_to_user:
        return person_id_to_user[person_id]
    
    print(f'WARNING: Did not find person {person_id} in member table, querying Notion Workspace')
    url = f"https://api.notion.com/v1/users/{person_id}"
    
    response = requests.get(url, headers=headers)
    ret = response.json()
    if ret['object'] == 'error':
        raise ValueError(f'Could not find member with person_id: {person_id}')

    person_id_to_user[person_id] = ret
    return ret


def get_attendance_table(page_id):
    url = f'https://api.notion.com/v1/blocks/{page_id}/children'
    
    response = requests.get(url, headers=headers)
    data = response.json()
    if data['object'] == 'error':
        raise ValueError(f'Could not find page {page_id}')
    
    blocks = data['results']

    table = None
    for block in blocks:
        if block['type'] == 'table':
            if table:
                raise ValueError('Found more than one table on Attendance sheet')
            else:
                table = block
    
    return table


def add_person_attendance(person_id):
    url = f"https://api.notion.com/v1/pages"

    if person_id in person_to_attendance_sheet:
        raise ValueError(f"Attendance sheet for id {person_id} already exists")

    member = get_person(person_id)
    name = member['name']

    # Create Attendance Page
    payload = {"parent": {"database_id":ATTENDANCE_TRACKER_DATABASE_ID},
                "properties": {
                    "Title" : {
                        "title": [
                            {
                                "text" : {
                                    "content" : f'{name}\'s Attendance'
                                }
                            }
                        ]
                    },
                    "Person" : {
                        "people" : [
                            {'object': 'user', 'id': member['id']}
                        ]
                    },
                    "Attended" : {
                        "number" : 0
                    },
                    "Late" : {
                        "number" : 0
                    },
                    "Approved Absence" : {
                        "number" : 0
                    },
                    "Excused Absence" : {
                        "number" : 0
                    },
                    "Unexcused Absence" : {
                        "number" : 0
                    }
                }}


    response = requests.post(url, json=payload, headers=headers)
    sheet = response.json()
    if sheet['object'] == 'error':
        raise ValueError(f'Unable to create attendance page for person_id {person_id} ({name})')

    # Add blocks to page
    page_id = sheet['id']
    url = f'https://api.notion.com/v1/blocks/{page_id}/children'
    payload = {
        "children" : [
            {
                "object" : "block",
                "type" : "table",
                "table" : {
                    "table_width": 5,
                    "has_column_header": True,
                    "has_row_header": True,
                    'children' : [
                        {
                            'type' : 'table_row',
                            'table_row': {'cells': 
                                [
                                [{'type': 'text',
                                    'text': {'content': 'Event Name', 'link': None}}],
                                [{'type': 'text',
                                    'text': {'content': 'Event ID', 'link': None}}],
                                [{'type': 'text',
                                    'text': {'content': 'Date', 'link': None}}],
                                [{'type': 'text',
                                    'text': {'content': 'Attendance Status', 'link': None}}],
                                [{'type': 'text',
                                    'text': {'content': 'Comments', 'link': None}}]
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    }

    response = requests.patch(url, json=payload, headers=headers)
    table = response.json()
    if table['object'] == 'error':
        raise ValueError('Could not create header row for attendance sheet table')
    
    person_to_attendance_sheet[person_id] = sheet
    person_to_attendance_table[person_id] = table


def get_attendance_table_rows(table_id):
    url = f'https://api.notion.com/v1/blocks/{table_id}/children'
    
    response = requests.get(url, headers=headers)

    data = response.json()
    if data['object'] == 'error':
        raise ValueError(f'Could not get table rows for table {table_id}')

    return data['results']


def load_person(s):
    person_id = s['properties']['Person']['people'][0]['id']
    person_to_attendance_sheet[person_id] = s 
    person_to_attendance_table[person_id] = get_attendance_table(s['id'])
    print(f"Loaded person {s['properties']['Person']['people'][0]['name']}")


def compose_row_json(event_name, event_id, date, attendance_status, comments=''):
    new_row = {
                'type' : 'table_row',
                'table_row': {'cells': 
                    [
                        [{'type': 'text',
                            'text': {'content': event_name, 'link': None}}],
                        [{'type': 'text',
                            'text': {'content': event_id, 'link': None}}],
                        [{'type': 'text',
                            'text': {'content': date, 'link': None}}],
                        [{'type': 'text',
                            'text': {'content': attendance_status, 'link': None}}],
                        [{'type': 'text',
                            'text': {'content': comments, 'link': None}}]
                    ]
                }
            }
    return new_row


def decompose_row_json(row):
    r = row['table_row']['cells']
    event_name = r[0][0]['text']['content']
    event_id = r[1][0]['text']['content']
    date = r[2][0]['text']['content']
    attendance_status = r[3][0]['text']['content']
    comments = r[4][0]['text']['content']

    return event_name, event_id, date, attendance_status, comments


def is_row_conflicting(row1, row2):
    event_name1 = row1['table_row']['cells'][0][0]['text']['content']
    event_id1 = row1['table_row']['cells'][1][0]['text']['content']
    date1 = row1['table_row']['cells'][2][0]['text']['content'][:10]
    attendance_status1 = row1['table_row']['cells'][3][0]['text']['content']
    # comments1 = row1['table_row']['cells'][4][0]['text']['content']

    event_name2 = row2['table_row']['cells'][0][0]['text']['content']
    event_id2 = row2['table_row']['cells'][1][0]['text']['content']
    date2 = row2['table_row']['cells'][2][0]['text']['content'][:10]
    attendance_status2 = row2['table_row']['cells'][3][0]['text']['content']
    # comments2 = row2['table_row']['cells'][4][0]['text']['content']

    return (event_id1 != event_id2) or (event_name1 != event_name2 or date1 != date2 or attendance_status1 != attendance_status2)


def add_attendance_table_rows(person_id, new_rows):
    table = person_to_attendance_table[person_id]
    table_id = table['id']
    url = f'https://api.notion.com/v1/blocks/{table_id}/children'

    existing_rows = get_attendance_table_rows(table_id)
    existing_rows_map = dict()
    
    for row in existing_rows[1:]:   # Ignore header row
        event_name, event_id, date, attendance_status, comments = decompose_row_json(row)
        existing_rows_map[event_id] = compose_row_json(event_name, event_id, date, attendance_status, comments)

    
    append_rows_map = dict()
    for row in new_rows:
        event_name, event_id, date, attendance_status = row
        comments = ''
        new_row = compose_row_json(event_name, event_id, date, attendance_status)
        if event_id in existing_rows_map:
            if is_row_conflicting(new_row, existing_rows_map[event_id]):
                print(new_row)
                print(existing_rows_map[event_id])
                print('Fix the conflict.')
                print('Select 0 to append the new row (you must manual delete the old row).')
                print('Select 1 to keep the existing row (new row will be ignored, fix attendance property on in the event)')
                i = ''
                while i not in ['0', '1']:
                    i = input('Select 0 or 1: ')

                if i == '0':
                    append_rows_map[event_id] = new_row
                    existing_rows_map[event_id] = new_row   # to prevent duplicate rows in new_rows
                else:
                    assert i == '1'

            # else:
            #     print(f'Ignoring equivalent row for event id {event_id}')
        else:
            append_rows_map[event_id] = new_row
            existing_rows_map[event_id] = new_row   # to prevent duplicate rows in new_rows

    date_int = lambda date: int(datetime.datetime.strptime(date[:10], "%Y-%m-%d").timestamp())
    update_rows = sorted(append_rows_map.values(), key = lambda row : date_int(row['table_row']['cells'][2][0]['text']['content']))

    payload = {
        'children' : list(update_rows)
    }


    response = requests.patch(url, json=payload, headers=headers)
    data = response.json()
    if data['object'] == 'error':
        print(data['message'])
        raise ValueError(f'Failed to update {table_id} with event {event_name}')


def update_attendance_counts(person_id, data):
    page = person_to_attendance_sheet[person_id]
    page_id = page['id']
    url = f'https://api.notion.com/v1/pages/{page_id}'

    payload = {
        "properties" : {
            "Attended" : {"number" : data['Attended']},
            "Late" : {"number" : data['Late']},
            "Approved Absence" : {"number" : data['Approved Absence']},
            "Excused Absence" : {"number" : data['Excused Absence']},
            "Unexcused Absence" : {"number" : data['Unexcused Absence']}
        }
    }

    response = requests.patch(url, json=payload, headers=headers)
    if response.json()['object'] != 'error':
        print(f'Updated attendance for person_id {person_id}')


def update_attendance(person_id, event_logs):
    p = get_person(person_id)
    print(f'Updating attendance for {p['name']} with id {person_id}')

    attendance_rows = []
    attendance_counter = {'Attended':0, 'Late':0, 'Approved Absence':0, 'Excused Absence':0, 'Unexcused Absence':0}

    for event_id, status in event_logs:
        event = event_id_to_event[event_id]
        props = event["properties"]
        title = props['Name']['title'][0]['plain_text']
        date = props['Date']['date']['start'][:10]
        attendance_rows.append((title, event_id, date, status))
        attendance_counter[status] += 1

        # print(f'- Marked {p['name']} as {status} for {title} on {date}')

    add_attendance_table_rows(person_id, attendance_rows)
    update_attendance_counts(person_id, attendance_counter)


def find_unexcused(page_id):
    url = f"https://api.notion.com/v1/databases/{EVENTS_DATABASE_ID}"
    response = requests.get(url, headers=headers)
    events_db = response.json()

    attended_prop_id = events_db['properties']['Attended']['id']
    late_prop_id = events_db['properties']['Late']['id']
    approved_absence_prop_id = events_db['properties']['Approved Absence']['id']
    excused_absence_prop_id = events_db['properties']['Excused Absence']['id']

    url = f"https://api.notion.com/v1/pages/{page_id}/properties/{attended_prop_id}"
    attended = requests.get(url, headers=headers).json()['results']
    attended = set([m['people']['id'] for m in attended])
    url = f"https://api.notion.com/v1/pages/{page_id}/properties/{late_prop_id}"
    late = requests.get(url, headers=headers).json()['results']
    late = set([m['people']['id'] for m in late])
    url = f"https://api.notion.com/v1/pages/{page_id}/properties/{approved_absence_prop_id}"
    approved_absence = requests.get(url, headers=headers).json()['results']
    approved_absence = set([m['people']['id'] for m in approved_absence])
    url = f"https://api.notion.com/v1/pages/{page_id}/properties/{excused_absence_prop_id}"
    excused_absence = requests.get(url, headers=headers).json()['results']
    excused_absence = set([m['people']['id'] for m in excused_absence])

    

    members = get_all_users()

    for member in members:
        tracked = attended | late | approved_absence | excused_absence
        if member['name'] not in ignored_users:
            if member['id'] not in tracked:
                print(member['name'])