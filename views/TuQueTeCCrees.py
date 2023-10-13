from flask import Blueprint, render_template

TQTC_bp = Blueprint('TQTC', __name__)

@TQTC_bp.route('/TQTC')
def tqtc():
    return render_template('TuQueTeCrees.html', title="TQTC")
