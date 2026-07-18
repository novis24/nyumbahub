# NyumbaHub

Mobile-first housing marketplace for Tanzania. Built with Django 5, Tailwind CSS, Alpine.js, and HTMX.

Tailwind (production)
---------------------
This project should not use the CDN in production. To build local Tailwind CSS:

1. Install Node dev dependency and build tool:

```bash
npm install
```

2. Build the CSS once or in CI:

```bash
npm run build:tailwind
```

The command outputs `static/css/tailwind.css` which is referenced by templates/base.html.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 5, PostgreSQL |
| Cache / Queue | Redis, Celery |
| Frontend | Django Templates, Tailwind CSS CDN, Alpine.js, HTMX |
| Media | Cloudinary |
| Static | Whitenoise |
| PWA | Service Worker + Web Manifest |

---

## Project structure

```
nyumbahub/
├── config/                  # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
├── apps/
│   ├── core/                # Home feed, middleware, context processors
│   ├── accounts/            # CustomUser, KYC, auth views
│   ├── listings/            # Listing model (rental/SME/auto), images, saved
│   ├── subscriptions/       # Plans, payment, billing
│   ├── notifications/       # In-app notifications
│   └── search/              # Search & filtering
├── templates/
│   ├── base.html            # Shell: top bar, bottom nav, desktop sidebar
│   ├── core/home.html       # Home feed
│   ├── accounts/            # signup, login, profile, settings
│   ├── listings/            # detail, create, my_listings, saved
│   ├── subscriptions/       # choose_plan, payment, manage
│   ├── notifications/       # list
│   ├── search/              # results
│   └── components/          # listing_card, listing_card_featured
├── static/
│   ├── manifest.json        # PWA manifest
│   └── sw.js                # Service worker
└── requirements.txt
```

---

## Setup

### 1. Clone and enter directory
```bash
cd nyumbahub
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your database, Cloudinary, and email credentials
```

### 5. Create PostgreSQL database
```bash
createdb nyumbahub
```

### 6. Run migrations
```bash
python manage.py makemigrations accounts listings subscriptions notifications
python manage.py migrate
```

### 7. Create superuser
```bash
python manage.py createsuperuser
```

### 8. Run the server
```bash
python manage.py runserver
```

### 9. (Optional) Run Celery for async tasks
```bash
# In a separate terminal
celery -A config worker -l info
```

---

## New packages to install

```bash
pip install django-htmx django-redis celery[redis] cloudinary django-cloudinary-storage \
            python-decouple phonenumbers django-phonenumber-field \
            django-crispy-forms crispy-tailwind whitenoise psycopg2-binary Pillow
```

---

## Progressive disclosure — how it works

| Feature | When it appears |
|---|---|
| Subscription/billing | Only in Settings → Listing & billing (providers only) |
| KYC / verification | Only in Settings → Identity verification (providers only) |
| Password change | Only in Settings → Security |
| Notification prefs | Only in Settings → Notifications |
| Post listing button | Only when provider has an active subscription |
| Contact landlord | Only when user is logged in and is a seeker |
| Filters panel | Hidden behind "Filters" button on search page |
| Listing actions | Hidden behind chevron on My Listings page |

---

## Account roles

| Role | Who | Can post listings | Pays |
|---|---|---|---|
| Seeker | Students / house hunters | No | Free |
| Landlord | Property owners | Rental only | Monthly subscription |
| SME | Business owners | SME listings | Monthly subscription |
| Auto | Vehicle dealers | Auto listings | Monthly subscription |

---

## Subscription plans (TZS)

| Plan | Price | Listings | Photos |
|---|---|---|---|
| Basic | 15,000/mo | 3 | 3 |
| Standard | 35,000/mo | 10 | 8 |
| Premium | 70,000/mo | Unlimited | 20 + Featured |

---

## Key design decisions

- **No React** — Django Templates + Alpine.js + HTMX gives a native-app feel with zero build tooling
- **Alpine.js** — used only for UI state: show/hide sheets, image previews, password toggles, radio selection. Nothing complex
- **HTMX** — used for infinite scroll on home feed, search filter updates, and HTMX partial swaps
- **Bottom nav** — fixed, safe-area aware, hides on desktop (sidebar takes over)
- **Progressive disclosure** — settings are layered; monetisation, verification, and security are never shown upfront
- **2-column grid** — all listing feeds are `grid-cols-2` mobile, expanding to 3-4 on desktop

---

## Activating KYC enforcement

When you're ready to require verification before posting, open `apps/core/middleware.py` and extend the `GATED_PATHS` check to also require `request.user.is_verified`.
