# River Watch — Test Credentials

These accounts exist in the MongoDB users collection on this preview environment.

## Super Admin
- Email: cdillerud@gmail.com
- Auth: Google OAuth (Emergent-managed) — no local password

## Vessel Owner
- Email: chaddillerud@gmail.com
- Password: test123

## Traffic Watch (observer)
- Email: trafficwatch@example.com
- Password: test123

Notes:
- Sessions are stored in `user_sessions` collection.
- `/planning` is wrapped in ProtectedRoute and requires any of the above to log in.
