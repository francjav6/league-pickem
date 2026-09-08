# League Pick'em — Vercel + FastAPI + Supabase/PostgreSQL

Arquitectura:

- `frontend/`: React + Vite → Vercel.
- `backend/`: FastAPI → Render.
- Base de datos: PostgreSQL → Supabase.
- Registro de picks actual + historial de cambios.
- Login por nombre + PIN.
- Vista de administrador con `ADMIN_KEY`.

## 1. Instalar en tu PC

Instala:

1. Python 3.12+
2. Node.js LTS
3. Git
4. VS Code (opcional)

Crea cuentas en GitHub, Supabase, Render y Vercel.

## 2. Probar localmente

### Backend

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Luego:

```bash
pip install -r requirements.txt
```

Copia `.env.example` como `.env` y deja inicialmente:

```env
DATABASE_URL=sqlite:///./pickem.db
SECRET_KEY=una-clave-larga
ADMIN_KEY=otra-clave-larga
CORS_ORIGINS=http://localhost:5173
```

Carga Week 1:

```bash
python seed.py
```

Arranca la API:

```bash
uvicorn main:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

### Frontend

En otra terminal:

```bash
cd frontend
npm install
```

Copia `.env.example` como `.env.local`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Ejecuta:

```bash
npm run dev
```

Abre:

```text
http://localhost:5173
```

## 3. Conectar Supabase

1. Crea un proyecto en Supabase.
2. Pulsa `Connect`.
3. Copia la conexión PostgreSQL.
4. Para Render, si la conexión directa da problemas de IPv4, usa el `Session pooler` de Supabase.
5. Pon la conexión únicamente en el backend:

```env
DATABASE_URL=postgresql://...
```

Nunca pongas `DATABASE_URL` en Vite/React.

Con la conexión de Supabase activa, ejecuta una vez:

```bash
python seed.py
```

Así se crean las tablas y se cargan los 7 matchups de Week 1.

## 4. Subir a GitHub

Desde la raíz:

```bash
git init
git add .
git commit -m "Initial League Pickem"
git branch -M main
git remote add origin TU_URL_GITHUB
git push -u origin main
```

## 5. Desplegar FastAPI en Render

En Render:

- New → Web Service
- Conecta el repo de GitHub
- Root Directory: `backend`
- Build Command:

```text
pip install -r requirements.txt
```

- Start Command:

```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Variables:

```text
DATABASE_URL = conexión Supabase
SECRET_KEY = cadena aleatoria larga
ADMIN_KEY = cadena aleatoria larga
CORS_ORIGINS = http://localhost:5173
```

Al terminar tendrás algo como:

```text
https://league-pickem-api.onrender.com
```

Prueba `/docs`.

## 6. Desplegar React en Vercel

En Vercel:

- Add New → Project
- Importa el mismo repo
- Root Directory: `frontend`
- Framework: Vite
- Variable:

```text
VITE_API_URL=https://TU-API.onrender.com
```

Deploy.

Vercel te dará algo como:

```text
https://mi-league-pickem.vercel.app
```

## 7. Autorizar la URL de Vercel

Vuelve a Render y cambia:

```text
CORS_ORIGINS=http://localhost:5173,https://mi-league-pickem.vercel.app
```

Guarda y redeploy.

## 8. Uso de los jugadores

Cada jugador:

1. Entra en la URL de Vercel.
2. Crea cuenta con nombre + PIN.
3. Ve Week 1.
4. Toca un equipo en cada matchup.
5. El pick se guarda inmediatamente.

Si cambia de elección antes del cierre:

- se actualiza el pick actual;
- se guarda el cambio en `pick_history`;
- se conserva fecha y hora.

## 9. Tu registro como administrador

En la web pulsa `Admin` e introduce el `ADMIN_KEY`.

Verás:

- jugador;
- matchup;
- pick actual;
- última modificación;
- historial completo de cambios.

Endpoints equivalentes:

```text
GET /admin/weeks/1/picks
GET /admin/weeks/1/history
```

Header:

```text
X-Admin-Key: TU_ADMIN_KEY
```

## 10. Bloquear picks

Automático por hora:

```text
PUT /admin/matchups/{id}/starts-at
```

```json
{
  "starts_at": "2026-09-10T00:00:00Z"
}
```

Manual:

```text
PUT /admin/matchups/{id}/lock
```

```json
{
  "locked": true
}
```

## 11. Cargar ganador

```text
PUT /admin/matchups/{id}/result
```

Equipo izquierdo:

```json
{
  "winner_choice": "A"
}
```

Equipo derecho:

```json
{
  "winner_choice": "B"
}
```

El leaderboard se obtiene en:

```text
GET /weeks/1/leaderboard
```

## Seguridad

No publiques jamás:

- `DATABASE_URL`
- contraseña de Supabase
- `SECRET_KEY`
- `ADMIN_KEY`

Solo `VITE_API_URL` va en el frontend.
