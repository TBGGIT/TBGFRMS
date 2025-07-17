from flask import Flask, render_template, request, redirect, session, url_for
import xmlrpc.client
import psycopg2
import json
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = '862992970d89d6d6a7f03204154a0e9fd69c489ff9a4334f5e696faf87a17780'

# Leer la URL base del sitio (para generar links públicos)
with open("conf.txt", "r") as f:
    BASE_URL = f.read().strip()

from cryptography.fernet import Fernet

# Cargar clave y desencriptar configuración
with open("key.key", "rb") as key_file:
    key = key_file.read()

fernet = Fernet(key)

with open("db.txt", "rb") as enc_file:
    encrypted_data = enc_file.read()

decrypted_data = fernet.decrypt(encrypted_data).decode()

# Ejecutar el código de configuración desencriptado
exec(decrypted_data)


# Conexión XML-RPC a Odoo

# RUTAS ------------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if password != 'tbg1212?':
            return render_template('login.html', error="Contraseña incorrecta")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Buscar al usuario por correo
        cur.execute("""
            SELECT id
            FROM res_users
            WHERE login = %s
        """, (username,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:
            user_id = user[0]
            session['uid'] = user_id
            session['username'] = username
            return redirect('/dashboard')

        return render_template('login.html', error="Correo no encontrado")

    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'uid' not in session:
        return redirect('/')

    uid = session['uid']
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    if uid in [1, 2, 3]:
        cur.execute("SELECT id, form_name, form_desc FROM x_formularios")
    else:
        cur.execute("SELECT id, form_name, form_desc FROM x_formularios WHERE user_creator = %s", (uid,))

    formularios = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('dashboard.html', formularios=formularios, username=session['username'], base_url=BASE_URL)

@app.route('/nuevo', methods=['GET', 'POST'])
def nuevo_formulario():
    if 'uid' not in session:
        return redirect('/')

    uid = session['uid']
    form_id = request.args.get('id')

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        x_user_seg = int(request.form['x_user_seg'])
        linkto = request.form['linkto'] or None
        fuente = request.form.get('fuente')

        preguntas = request.form.getlist('preguntas[]')

        if form_id:
            cur.execute("""
                UPDATE x_formularios
                SET form_name = %s,
                    form_desc = %s,
                    x_user_seg = %s,
                    form_questions = %s,
                    linkto = %s,
                    fuente = %s
                WHERE id = %s
            """, (titulo, descripcion, x_user_seg, json.dumps(preguntas), linkto, fuente, form_id))
        else:
            cur.execute("""
                INSERT INTO x_formularios (user_creator, user_id, x_user_seg, form_name, form_desc, form_questions, linkto)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (uid, uid, x_user_seg, titulo, descripcion, json.dumps(preguntas), linkto))
            form_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()
        return render_template('form_guardado.html', link=f"{BASE_URL}/f/{form_id}")

    # Si es GET, cargar datos para edición
    titulo = descripcion = linkto = ''
    x_user_seg = None
    preguntas = []

    if form_id:
        cur.execute("SELECT form_name, form_desc, x_user_seg, form_questions, linkto FROM x_formularios WHERE id = %s", (form_id,))
        row = cur.fetchone()
        if row:
            titulo, descripcion, x_user_seg, preguntas_json, linkto = row
            if isinstance(preguntas_json, str):
                preguntas = json.loads(preguntas_json)
            elif isinstance(preguntas_json, list):
                preguntas = preguntas_json

    # Obtener usuarios
    cur.execute("""
        SELECT u.id, p.name
        FROM res_users u
        JOIN res_partner p ON u.partner_id = p.id
        WHERE u.share = FALSE
        ORDER BY p.name
    """)
    users = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    # Obtener estados
    cur.execute("""
        SELECT id, name FROM res_country_state
        ORDER BY
            CASE WHEN country_id = (SELECT id FROM res_country WHERE code = 'MX') THEN 0 ELSE 1 END,
            name
    """)

    estados = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('nuevo.html',
                           titulo=titulo,
                           descripcion=descripcion,
                           x_user_seg=x_user_seg,
                           preguntas=preguntas,
                           linkto=linkto,
                           users=users,
                           estados=estados)



@app.route('/f/<form_id>', methods=['GET', 'POST'])
def ver_formulario_publico(form_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT form_name, form_desc, form_questions, user_id, x_user_seg, linkto FROM x_formularios WHERE id = %s", (form_id,))
    result = cur.fetchone()

    if not result:
        cur.close()
        conn.close()
        return "Formulario no encontrado", 404

    form_name, form_desc, preguntas_json, user_id, x_user_seg, linkto = result

    if isinstance(preguntas_json, str):
        preguntas = json.loads(preguntas_json)
    elif isinstance(preguntas_json, list):
        preguntas = preguntas_json
    else:
        preguntas = []

    # Obtener lista de estados
    cur.execute("""
        SELECT id, name FROM res_country_state
        ORDER BY
            CASE WHEN country_id = (SELECT id FROM res_country WHERE code = 'MX') THEN 0 ELSE 1 END,
            name
    """)

    estados = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    if request.method == 'POST':
        nombre = request.form['nombre']
        empresa = request.form['empresa']
        puesto = request.form['puesto']
        correo = request.form['correo']
        telefono = request.form['telefono']
        fuente = request.form.get('fuente')
        linkedin_url = request.form.get('linkedin_url')
        estado_id = int(request.form.get('estado_id'))

        respuestas = []
        for pregunta in preguntas:
            respuesta = request.form.get(pregunta, '')
            respuestas.append(f"{pregunta}\n{respuesta}")

        descripcion_final = "\n\n".join(respuestas)

        fuente_final = f"{fuente} - {form_name}" if fuente else form_name

        now = datetime.now()
        cur.execute("""
            INSERT INTO crm_lead (
                name, contact_name, email_from, phone, partner_name, description,
                user_id, x_user_seg, type, stage_id, team_id, active,
                create_date, write_date, x_fuentecontacto, x_url, state_id
            ) VALUES (%s, %s, %s, %s, %s, %s,
                      %s, %s, 'opportunity', 1, 1, TRUE,
                      %s, %s, %s, %s, %s)
        """, (
            f"Contacto Web: {nombre}", nombre, correo, telefono, empresa,
            descripcion_final, user_id, x_user_seg,
            now, now, fuente_final, linkedin_url, estado_id
        ))

        conn.commit()
        cur.close()
        conn.close()

        if linkto and linkto.startswith(('http://', 'https://')):
            return redirect(linkto)
        return redirect(url_for('gracias'))

    cur.close()
    conn.close()

    return render_template('public_form.html',
                           form_name=form_name,
                           form_desc=form_desc,
                           preguntas=preguntas,
                           estados=estados)


@app.route('/editar/<int:form_id>', methods=['GET', 'POST'])
def editar_formulario(form_id):
    if 'uid' not in session:
        return redirect('/')

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    if request.method == 'POST':
        # Guardar los cambios
        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        x_user_seg = int(request.form['x_user_seg'])
        linkto = request.form['linkto'] or None
        fuente = request.form.get('fuente')
        linkedin_url = request.form.get('linkedin_url')
        estado_id = int(request.form.get('estado_id'))

        preguntas = request.form.getlist('preguntas[]')

        cur.execute("""
            UPDATE x_formularios
            SET form_name = %s,
                form_desc = %s,
                x_user_seg = %s,
                form_questions = %s,
                linkto = %s
            WHERE id = %s
        """, (titulo, descripcion, x_user_seg, json.dumps(preguntas), linkto, form_id))
        conn.commit()
        cur.close()
        conn.close()

        return redirect('/dashboard')

    # Obtener los datos actuales para precargar el formulario
    cur.execute("SELECT form_name, form_desc, x_user_seg, form_questions, linkto FROM x_formularios WHERE id = %s", (form_id,))
    row = cur.fetchone()

    if not row:
        return "Formulario no encontrado", 404

    titulo, descripcion, x_user_seg, preguntas_json, linkto = row
    if isinstance(preguntas_json, str):
        preguntas = json.loads(preguntas_json)
    elif isinstance(preguntas_json, list):
        preguntas = preguntas_json
    else:
        preguntas = []


    # Obtener lista de usuarios
    cur.execute("""
        SELECT u.id, p.name
        FROM res_users u
        JOIN res_partner p ON u.partner_id = p.id
        WHERE u.share = FALSE
        ORDER BY p.name
    """)
    users = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('nuevo.html',
        editando=True,
        form_id=form_id,
        titulo=titulo,
        descripcion=descripcion,
        x_user_seg=x_user_seg,
        linkto=linkto,
        preguntas=preguntas,
        users=users)


@app.route('/gracias')
def gracias():
    return render_template('gracias.html')

# Ejecutar en puerto 5001
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=False)
