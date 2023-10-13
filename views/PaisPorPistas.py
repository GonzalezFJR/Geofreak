from flask import Blueprint, render_template
from flask import request, jsonify

P3_bp = Blueprint('P3', __name__)

def clean_country_name(name):
    """Función para limpiar el nombre del país"""
    return name.replace("**", "").strip()

def txt_to_dicts(txt_content):
    # Dividir el contenido por la secuencia '\n\n**'
    countries_data = [data for data in txt_content.split("\n\n**") if data]
    
    # Lista para almacenar los diccionarios
    countries_list = []
    
    for country_data in countries_data:
        # Dividir la información de cada país por '\n' (nueva línea)
        lines = [line for line in country_data.strip().split("\n") if line]
        
        # Extraer el nombre del país y los puntos relevantes
        country_name = clean_country_name(lines[0].replace(":", ""))
        points = lines[1:]
        
        # Crear un diccionario para el país
        country_dict = {
            "country": country_name,
            "points": [point.split(". ")[1].strip() for point in points]
        }
        
        countries_list.append(country_dict)
    
    return countries_list

# Leer el archivo .txt
with open("ppp.txt", "r", encoding="utf-8") as file:
    content = file.read()
data = txt_to_dicts(content)

@P3_bp.route('/country/<int:index>/', methods=['GET', 'POST'])
def country_view(index):
    if index < 0:
        index = len(data) - 1
    elif index >= len(data):
        index = 0
    country_data = data[index]
    if request.method == "POST":
        hint_index = int(request.form.get('hint_index', 0))
        if hint_index < len(country_data['points']):
            return jsonify({'hint': country_data['points'][hint_index], 'hint_index': hint_index+1})
        else:
            return jsonify({'error': 'No more hints available'}), 400
    return render_template('PaisPorPistas.html', country=country_data, index=index, total=len(data))


@P3_bp.route('/P3')
def P3():
    return render_template('PaisPorPistas.html', country=data[0], index=0, total=len(data) - 1)
