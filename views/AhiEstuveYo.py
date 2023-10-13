from flask import Blueprint, render_template

AhiEstuveYo_bp = Blueprint('AhiEstuveYo', __name__)

@AhiEstuveYo_bp.route('/AhiEstuveYo')
def page2():
    return render_template('AhiEstuveYo.html', title="Ahí estuve yo")
