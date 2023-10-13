from flask import Blueprint, render_template

HM3_bp = Blueprint('HM3', __name__)

@HM3_bp.route('/HM3')
def HM3():
    return render_template('HolaMundo3.html', title="HM3")
