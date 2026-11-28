# Rotating the staging read-only password

`STAGING_RO_URL` holds a database password that expires every 90 days. Only
an owner of the tally-app organisation can rotate it: the database's console
asks for the owner's passkey.

1. Console, project `tally-staging`, Roles, `readonly`, Reset password.
2. Put the new URL in the team vault entry "staging read-only" and in the
   CI secret `STAGING_RO_URL`.
3. `make smoke-staging` on any branch reads through the new URL.

Until it is rotated nothing breaks; after the expiry date every staging read
fails, the smoke and the nightly BI import included.
