from flask import Blueprint, render_template

perdidos_bp = Blueprint('Perdidos', __name__)

@perdidos_bp.route('/Perdidos')
def perdidos():
    return render_template('Perdidos.html', title="Perdidos")
