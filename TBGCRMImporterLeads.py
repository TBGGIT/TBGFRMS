from flask import Flask, render_template_string, request, redirect, session, send_file
import pandas as pd
import psycopg2
from cryptography.fernet import Fernet
import json

# --- Cargar configuración segura (bd, url, etc.) ---
with open("key.key", "rb") as key_file:
    key = key_file.read()

fernet = Fernet(key)
with open("db.txt", "rb") as enc_file:
    encrypted_data = enc_file.read()

decrypted_data = fernet.decrypt(encrypted_data).decode()
exec(decrypted_data)

# --- Configurar Flask ---
app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',   # <-- Corregido para entorno local (evita problemas de sesión)
    SESSION_COOKIE_SECURE=False      # <-- Desactiva HTTPS-only en local
)

# --- HTML: Login ---
login_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <style>
        body {
            background-image: url('/static/background.png');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center;
            font-family: Arial, sans-serif;
            min-height: 100vh;
            margin: 0;
        }
        .container { max-width: 400px; margin: auto; margin-top: 100px; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        input, button { width: 100%; padding: 10px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Iniciar Sesión</h2>
        <form method="POST">
            <input type="email" name="email" placeholder="Correo" required>
            <input type="password" name="apppassword" placeholder="Contraseña" required>
            <button type="submit">Entrar</button>
        </form>
        {% if error %}<p style="color:red; text-align:center;"><strong>{{ error }}</strong></p>{% endif %}
    </div>
</body>
</html>
"""

# --- HTML: Página principal de importación ---
main_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Subir Leads</title>
    <style>
        body {
            background-image: url('/static/background.png');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center;
            font-family: Arial, sans-serif;
            min-height: 100vh;
            margin: 0;
        }
        .container { max-width: 600px; margin: auto; margin-top: 50px; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        input, button { width: 100%; padding: 10px; margin: 10px 0; }
        .top-buttons { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .top-buttons a, .top-buttons form { display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="top-buttons">
            <a href="/descargar_plantilla"><button type="button">Descargar Plantilla</button></a>
            <form method="GET" action="/logout"><button type="submit">Cerrar Sesión</button></form>
        </div>
        <h2>Subir Archivo de Leads</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv, .xlsx" required>
            <button type="submit">Subir</button>
        </form>
        {% if success %}<p style="color:green; text-align:center;"><strong>{{ success }}</strong></p>{% endif %}
    </div>
</body>
</html>
"""

# --- Ruta: Login ---
@app.route('/', methods=['GET', 'POST'])
def login():
    # Si ya hay sesión activa, redirige directamente
    if 'user_id' in session:
        return redirect('/main')

    error = None
    if request.method == 'POST':
        email = request.form['email']
        apppassword = request.form['apppassword']
        print("Login intento:", email, apppassword)

        try:
            conn = psycopg2.connect(**ODOO_DB_CONFIG)
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM res_users WHERE login = %s AND x_apppassword = %s
            """, (email, apppassword))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                session['user_id'] = row[0]
                session['email'] = email
                print("Login exitoso → redirigiendo a /main")
                return redirect('/main')
            else:
                error = "Correo o contraseña incorrectos."
                print("Login fallido")

        except Exception as e:
            error = f"Error de conexión: {str(e)}"
            print("Error de conexión:", error)

    return render_template_string(login_template, error=error)


# --- Ruta: Logout ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --- Ruta: Página principal de importación ---
@app.route('/main', methods=['GET', 'POST'])
def main():
    if 'user_id' not in session:
        return redirect('/')
    
    success = None
    if request.method == 'POST':
        file = request.files['file']
        if file:
            filename = file.filename
            df = pd.read_excel(file) if filename.endswith('.xlsx') else pd.read_csv(file)
            df = df.fillna('')
            df['Nombre completo'] = df.get('Nombre', '') + ' ' + df.get('Apellidos', '')
            df['Pais'] = df.get('Pais', '')
            df['Ciudad'] = df.get('Ciudad', '')
            df['Descripcion'] = df.get('Descripcion', '')
            df['name'] = 'contacto'
            df['user_id'] = session['user_id']

            conn = psycopg2.connect(**ODOO_DB_CONFIG)
            cur = conn.cursor()

            for _, row in df.iterrows():
                empresa = row.get('Empresa', '').strip()

                # Buscar si ya existe un lead para la misma empresa
                cur.execute("""
                    SELECT id FROM crm_lead 
                    WHERE partner_name = %s AND user_id = %s 
                    LIMIT 1
                """, (empresa, row['user_id']))
                existing_lead = cur.fetchone()


                if existing_lead:
                    lead_id = existing_lead[0]
                    # Buscar country_id

                    pais_nombre = row.get('Pais', '')
                    cur.execute("SELECT id FROM res_country WHERE name->>'es_MX' = %s LIMIT 1", (pais_nombre,))
                    country = cur.fetchone()
                    country_id = country[0] if country else None

                    # Crear contacto adicional
                    cur.execute("""
                        INSERT INTO res_partner (
                            name, complete_name, email, phone, function,
                            country_id, city, comment,
                            create_uid, write_uid, company_id, is_company, type, active
                        )
                        VALUES (%s, %s, %s, %s, %s, 
                                %s, %s, %s, 
                                %s, %s, 1, FALSE, 'contact', TRUE)
                        RETURNING id
                    """, (
                        row['Nombre completo'],
                        row['Nombre completo'],
                        row.get('email', ''),
                        row.get('celular', ''),
                        row.get('Puesto', ''),
                        country_id,
                        row.get('Ciudad', ''),
                        row.get('Descripcion', ''),
                        row['user_id'],
                        row['user_id']
                    ))
                    partner_id = cur.fetchone()[0]

                    # Relacionar contacto al lead como contacto adicional
                    cur.execute("""
                        INSERT INTO x_crm_lead_res_partner_rel (crm_lead_id, res_partner_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (lead_id, partner_id))
                    print(f"✓ Contacto adicional insertado: Lead ID = {lead_id}, Partner ID = {partner_id}")



                else:
                    # Buscar country_id (si no se hizo antes)
                    pais_valor = row.get('Pais', '')
                    if isinstance(pais_valor, dict):
                        pais_nombre = ''
                    elif pd.isna(pais_valor):
                        pais_nombre = ''
                    else:
                        pais_nombre = str(pais_valor).strip()
                        
                    cur.execute("SELECT id FROM res_country WHERE name->>'es_MX' = %s LIMIT 1", (pais_nombre,))
                    country = cur.fetchone()
                    country_id = country[0] if country else None

                    # Insertar nuevo lead completo
                    cur.execute("""
                        INSERT INTO crm_lead (
                            name, contact_name, email_from, phone, function, partner_name,
                            x_fuentecontacto, user_id, create_uid, write_uid, create_date, write_date,
                            type, message_bounce, team_id, company_id, stage_id, color, priority, active,
                            country_id, city, description
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now(),
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s)
                    """, (
                        row['name'],
                        row['Nombre completo'],
                        row.get('email', ''),
                        row.get('celular', ''),
                        row.get('Puesto', ''),
                        row.get('Empresa', ''),
                        row.get('fuente', ''),
                        row['user_id'],
                        row['user_id'],
                        row['user_id'],
                        'opportunity',
                        0, 1, 1, 1, 0, 0, True,
                        country_id,
                        row.get('Ciudad', ''),
                        row.get('Descripcion', '')
                    ))


            conn.commit()
            cur.close()
            conn.close()
            success = "✅ Leads subidos exitosamente."

    return render_template_string(main_template, success=success)


# --- Ruta: Descargar plantilla de ejemplo ---
@app.route('/descargar_plantilla')
def descargar_plantilla():
    return send_file('TBGCRMplantilla.xlsx', as_attachment=True)

# --- Ejecutar servidor Flask ---
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5015, debug=False)
