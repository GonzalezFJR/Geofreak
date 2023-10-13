from flask import Blueprint, render_template
import json

HM1_bp = Blueprint('HM1', __name__)

def txt_to_dic_HM1(fname='HM1.txt'):
    with open(fname, 'r', encoding='utf-8') as f:
        text = f.read()
    # Splitting the text by question delimiter
    blocks = text.split("- Pregunta: ")[1:]

    questions = []

    for block in blocks:
        # Splitting each block by newline to separate individual components
        lines = [line.strip() for line in block.split('\n') if line.strip()]

        # Extracting the question
        question = lines[0]

        # Extracting options
        options = [option.strip() for option in lines[1].replace("Opciones:", "").split(",")]

        # Extracting answer
        answer = lines[2].replace("Respuesta:", "").strip()

        # Extracting description
        description = lines[3].replace("Descripción:", "").strip()

        # Building the dictionary
        q_dict = {
            "Pregunta": question,
            "Opciones": options,
            "Respuesta": answer,
            "Descripción": description
        }

        questions.append(q_dict)
    return questions

@HM1_bp.route('/HM1')
def HM1():
    preguntas = txt_to_dic_HM1('HM1.txt')
    return render_template('HolaMundo1.html', preguntas=preguntas)
