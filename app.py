from flask import Flask, render_template
import json
from flask import jsonify, request

app = Flask(__name__)
app.secret_key = 'asdfasin43n34Q$TQJ4qt4t$OQTqtOQ$T'  # For session handling

# Importing blueprints
from views.home import home_bp
from views.HM1 import HM1_bp
from views.HM2 import HM2_bp
from views.HM3 import HM3_bp
from views.AhiEstuveYo import AhiEstuveYo_bp
from views.PaisPorPistas import P3_bp
from views.Perdidos import perdidos_bp
from views.TeCuentoComoPaso import TCCP_bp 
from views.TuQueTeCCrees import TQTC_bp

app.register_blueprint(home_bp)
app.register_blueprint(HM1_bp)
app.register_blueprint(HM2_bp)
app.register_blueprint(HM3_bp)
app.register_blueprint(AhiEstuveYo_bp)
app.register_blueprint(P3_bp)
app.register_blueprint(perdidos_bp)
app.register_blueprint(TCCP_bp)
app.register_blueprint(TQTC_bp)

@app.route('/')
def index():
    return render_template('base.html')


def LoadJsonSafe(fname='counters.json'):
    try:
        with open(fname, 'r') as f:
            counters = json.load(f)
    except:
        with open(fname, 'r') as f:
            counters = f.read()
        if counters.endswith('}}'):
            counters = counters[:-1]
            with open(fname, 'w') as f:
                f.write(counters)
            counters = json.loads(counters)
        else:
            counters = {}
            with open(fname, 'w') as f:
                json.dump(counters, f)
    return counters
            

@app.route('/get_counters')
def get_counters():
    #with open('counters.json', 'r') as f:
    #    counters = json.load(f)
    counters = LoadJsonSafe()
    return jsonify(counters)

@app.route('/update_counter', methods=['POST'])
def update_counter():
    button_id = request.json.get('button_id')
    value = request.json.get('value')

    #with open('counters.json', 'r') as f:
    #    counters = json.load(f)
    counters = LoadJsonSafe()
    
    counters[button_id] = value

    with open('counters.json', 'w') as f:
        json.dump(counters, f)

    return jsonify(success=True)





if __name__ == '__main__':
    app.run(debug=True)
