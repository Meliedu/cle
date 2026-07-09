// Dev-only: seed Better Auth credential rows for the demo accounts so they can
// sign in with email/password through the real UI. Creates auth.user (with
// emailVerified=true to bypass the requireEmailVerification gate) + auth.account
// (providerId 'credential', bcrypt hash) using the SAME deterministic ids as
// backend/seed_demo.py, so JWT `sub` == public.users.better_auth_id.
//
// Idempotent: deletes prior rows for the demo emails, then recreates them.
// Refuses to run when NODE_ENV=production.
//
// Run from frontend/:  node scripts/seed-auth.mjs
import { Pool } from "pg";
import bcrypt from "bcrypt";

if (process.env.NODE_ENV === "production") {
  console.error("Refusing to seed demo auth with NODE_ENV=production.");
  process.exit(1);
}

const PASSWORD = "MeliDemo2026!";
const USERS = [
  { id: "demo-teacher", email: "meli.teacher@ust.hk", name: "Dr. Wei Chen" },
  { id: "demo-student", email: "meli.student@connect.ust.hk", name: "Aidan Lam" },
  { id: "demo-student-2", email: "meli.pending@connect.ust.hk", name: "Priya Nair" },
];

const databaseUrl =
  process.env.BETTER_AUTH_DATABASE_URL ??
  process.env.DATABASE_URL ??
  "postgresql://postgres:postgres@localhost:5432/langassistant";

const pool = new Pool({
  connectionString: databaseUrl,
  options: "-c search_path=auth,public",
});

async function main() {
  const hash = await bcrypt.hash(PASSWORD, 12);
  const emails = USERS.map((u) => u.email);

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // Clear prior demo rows (account rows reference user via userId).
    await client.query(`DELETE FROM auth.account WHERE "userId" = ANY($1)`, [
      USERS.map((u) => u.id),
    ]);
    await client.query(`DELETE FROM auth.user WHERE email = ANY($1)`, [emails]);

    for (const u of USERS) {
      await client.query(
        `INSERT INTO auth."user" (id, name, email, "emailVerified", "createdAt", "updatedAt")
         VALUES ($1, $2, $3, true, now(), now())`,
        [u.id, u.name, u.email],
      );
      await client.query(
        `INSERT INTO auth.account
           (id, "accountId", "providerId", "userId", password, "createdAt", "updatedAt")
         VALUES ($1, $2, 'credential', $3, $4, now(), now())`,
        [`${u.id}-cred`, u.id, u.id, hash],
      );
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }

  console.log("Auth seed complete — sign in with any of:");
  for (const u of USERS) console.log(`  ${u.email}  /  ${PASSWORD}`);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
