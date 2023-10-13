from flask import Blueprint, render_template
from flask import render_template, request, session, redirect, url_for
import json

HM2_bp = Blueprint('HM2', __name__)

def txt_to_dic_HM2(fname='HM2.txt'):
    with open(fname, 'r', encoding='utf-8') as f:
        text = f.read()
    # Splitting the text by criterion delimiter
    blocks = text.split("- Criterio: ")[1:]
    data = {}
    
    for block in blocks:
        # Splitting each block by newline to separate individual components
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        # Extracting the criterion
        criterion = lines[0]
        
        # Extracting key-value pairs for each country
        countries_data = {}
        for line in lines[1:]:
            country, value = line.split(":")
            countries_data[country.strip()] = float(value.strip())
            
        # Checking if the criterion is already in the dictionary
        if criterion in data:
            if isinstance(data[criterion], list):
                data[criterion].append(countries_data)
            else:
                data[criterion] = [data[criterion], countries_data]
        else:
            data[criterion] = countries_data
    
    return data

def read_json_file(file_path):
    """
    Reads a .json file and returns a list of simple dictionaries and a list of criteria.
    """
    if isinstance(file_path, str):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = file_path
    
    criteria_list = [] #list(data.keys())
    dict_list = []
    
    for criterion, values in data.items():
        if isinstance(values, list):  # If the criterion has multiple dictionaries
            dict_list.extend(values)
            criteria_list.extend([criterion] * len(values))
        else:
            dict_list.append(values)
            criteria_list.append(criterion)

    return dict_list, criteria_list





def order_countries_by_value(data_dict):
    """
    Returns a list of country names ordered by their values in descending order.
    """
    return [k for k, v in sorted(data_dict.items(), key=lambda item: item[1], reverse=True)]

def get_score(data_dict, country_list):
    """
    Compares the provided country list with the sorted list and assigns a score based on the position of each country.
    """
    # Generate the correct order
    correct_order = order_countries_by_value(data_dict)
    
    score = 0
    for i, country in enumerate(country_list):
        if country in correct_order:
            distance = abs(i - correct_order.index(country))
            if distance == 0:
                score += 4
            elif distance == 1:
                score += 2
            elif distance == 2:
                score += 1
            elif distance == 3:
                score -= 1
            elif distance == 4:
                score -= 3
                
    return max(score, 0)

#data_dicts, titles = read_json_file('HM2.json')
data_dicts, titles = read_json_file(txt_to_dic_HM2('HM2.txt'))
print('titles = ', titles)
print('data dicts = ', data_dicts)

@HM2_bp.route('/HM2/navigate/<direction>', methods=['POST'])
def navigate(direction):
    if direction == "next":
        session['current_index'] = (session['current_index'] + 1)
    elif direction == "previous":
        session['current_index'] -= 1

    # Ensure we don't go out of bounds
    session['current_index'] = max(0, min(len(titles)-1, session['current_index']))
    
    return redirect(url_for('HM2.HM2'))

@HM2_bp.route('/HM2/submit', methods=['POST'])
def submit():
    ordered_items = request.form.get('items').split(',')
    score = get_score(data_dicts[session['current_index']], ordered_items)
    return str(score)

@HM2_bp.route('/HM2')
def HM2():
    if 'current_index' not in session:
        session['current_index'] = 0
    idx = session['current_index']
    total_pages = len(titles)
    current_page = idx+1
    return render_template('HolaMundo2.html', title=titles[idx], items=list(data_dicts[idx].keys()), total_pages=total_pages, current_page=current_page)
