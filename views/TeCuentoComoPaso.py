from flask import Blueprint, render_template

TCCP_bp = Blueprint('TCCP', __name__)

@TCCP_bp.route('/TCCP')
def tccp():
    return render_template('TeCuentoComoPaso.html', title="TCCP")
