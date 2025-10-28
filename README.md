**  X402 SOL BET  **

** HOW IT WORKS  ** 
├─ .github/workflows/ci.yml
├─ docker-compose.yml
├─ Dockerfile
├─ README.md
├─ package.json
├─ tsconfig.json
├─ jest.config.js
├─ src/
│  ├─ index.ts
│  ├─ app.ts
│  ├─ config.ts
│  ├─ routes/
│  │  ├─ auth.ts
│  │  ├─ events.ts
│  │  ├─ markets.ts
│  │  ├─ bets.ts
│  ├─ controllers/
│  │  ├─ authController.ts
│  │  ├─ eventController.ts
│  │  ├─ marketController.ts
│  │  ├─ betController.ts
│  ├─ services/
│  │  ├─ authService.ts
│  │  ├─ eventService.ts
│  │  ├─ marketService.ts
│  │  ├─ betService.ts
│  ├─ db/
│  │  ├─ index.ts
│  │  ├─ migrations/
│  │  │  └─ create_schema.sql
│  ├─ middleware/
│  │  ├─ auth.ts
│  │  ├─ errorHandler.ts
│  ├─ types/
│  │  └─ index.d.ts
├─ tests/
│  └─ bet.test.ts{

** HOW TO START **
  "name": "x402-betting",
  "version": "0.1.0",
  "description": "Starter for x402 sports betting system",
  "main": "dist/index.js",
  "scripts": {
    "start": "ts-node-dev --respawn --transpile-only src/index.ts",
    "build": "tsc",
    "lint": "eslint . --ext .ts",
    "test": "jest --coverage",
    "migrate": "psql $DATABASE_URL -f src/db/migrations/create_schema.sql"
  },
  "dependencies": {
    "bcrypt": "^5.1.0",
    "body-parser": "^1.20.2",
    "dotenv": "^16.3.1",
    "express": "^4.18.2",
    "express-validator": "^7.0.1",
    "jsonwebtoken": "^9.0.2",
    "pg": "^8.11.0",
    "uuid": "^9.0.0"
  },
  "devDependencies": {
    "@types/bcrypt": "^5.0.0",
    "@types/express": "^4.17.17",
    "@types/jest": "^29.5.3",
    "@types/jsonwebtoken": "^9.0.2",
    "@types/node": "^20.5.1",
    "jest": "^29.6.1",
    "ts-jest": "^29.1.1",
    "ts-node-dev": "^2.0.0",
    "typescript": "^5.5.6"
  }
}
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
import dotenv from 'dotenv';
dotenv.config();

export default {
  port: process.env.PORT || 4000,
  jwtSecret: process.env.JWT_SECRET || 'change-me',
  dbUrl: process.env.DATABASE_URL || 'postgres://postgres:postgres@db:5432/x402'
};
import { Pool } from 'pg';
import config from '../config';

export const pool = new Pool({
  connectionString: config.dbUrl
});

export async function query(text: string, params?: any[]) {
  const res = await pool.query(text, params);
  return res;
}
-- Users
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  balance NUMERIC(14,2) NOT NULL DEFAULT 0.00,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Events (sporting events)
CREATE TABLE IF NOT EXISTS events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'upcoming', -- upcoming | live | finished | cancelled
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Markets (e.g., "Match winner", "Total goals over/under")
CREATE TABLE IF NOT EXISTS markets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  spec JSONB DEFAULT '{}', -- structure depends on market type
  status TEXT NOT NULL DEFAULT 'open', -- open | suspended | closed
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Odds (for selection/outcome)
CREATE TABLE IF NOT EXISTS odds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id UUID REFERENCES markets(id) ON DELETE CASCADE,
  label TEXT NOT NULL, -- e.g., "Home", "Away", "Over 2.5"
  price NUMERIC(10,4) NOT NULL, -- decimal odds for simplicity
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Bets
CREATE TABLE IF NOT EXISTS bets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  market_id UUID REFERENCES markets(id),
  odds_id UUID REFERENCES odds(id),
  stake NUMERIC(14,2) NOT NULL,
  potential_return NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL DEFAULT 'placed', -- placed | settled | void | cancelled
  placed_at TIMESTAMPTZ DEFAULT now(),
  settled_at TIMESTAMPTZ,
  result JSONB DEFAULT '{}'
);

-- index helpers
CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events (starts_at);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import config from '../config';

export interface AuthRequest extends Request {
  user?: { id: string; role: string; username?: string };
}

export function requireAuth(req: AuthRequest, res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  if (!header) return res.status(401).json({ error: 'Missing Authorization' });
  const parts = header.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer') return res.status(401).json({ error: 'Malformed Authorization' });
  try {
    const payload = jwt.verify(parts[1], config.jwtSecret) as any;
    req.user = { id: payload.id, role: payload.role, username: payload.username };
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

export function requireRole(role: string) {
  return function (req: AuthRequest, res: Response, next: NextFunction) {
    if (!req.user) return res.status(401).json({ error: 'Unauthorized' });
    if (req.user.role !== role) return res.status(403).json({ error: 'Insufficient permissions' });
    next();
  };
}
import { Request, Response, NextFunction } from 'express';

export function errorHandler(err: any, req: Request, res: Response, next: NextFunction) {
  console.error(err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal server error'
  });
}
import { Request, Response } from 'express';
import { query } from '../db';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import config from '../config';

export async function register(req: Request, res: Response) {
  const { username, email, password } = req.body;
  if (!username || !email || !password) return res.status(400).json({ error: 'Missing fields' });

  const hash = await bcrypt.hash(password, 10);
  const dbRes = await query(
    'INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3) RETURNING id, username, email, role, balance',
    [username, email, hash]
  );
  const user = dbRes.rows[0];
  res.status(201).json(user);
}

export async function login(req: Request, res: Response) {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: 'Missing fields' });

  const dbRes = await query('SELECT id, username, password_hash, role FROM users WHERE username=$1', [username]);
  const user = dbRes.rows[0];
  if (!user) return res.status(401).json({ error: 'Invalid credentials' });

  const ok = await bcrypt.compare(password, user.password_hash);
  if (!ok) return res.status(401).json({ error: 'Invalid credentials' });

  const token = jwt.sign({ id: user.id, role: user.role, username: user.username }, config.jwtSecret, { expiresIn: '8h' });
  res.json({ token });
}
import { Request, Response } from 'express';
import { query } from '../db';
import { AuthRequest } from '../middleware/auth';

export async function placeBet(req: AuthRequest, res: Response) {
  const { odds_id, stake } = req.body;
  if (!odds_id || !stake) return res.status(400).json({ error: 'Missing fields' });
  const userId = req.user!.id;

  // fetch odds and market
  const oddsRes = await query('SELECT o.id, o.price, o.market_id, m.status as market_status FROM odds o JOIN markets m ON o.market_id = m.id WHERE o.id=$1', [odds_id]);
  const odds = oddsRes.rows[0];
  if (!odds) return res.status(404).json({ error: 'Odds not found' });
  if (odds.market_status !== 'open') return res.status(400).json({ error: 'Market not open for betting' });

  // check balance
  const userRes = await query('SELECT balance FROM users WHERE id=$1', [userId]);
  const user = userRes.rows[0];
  if (!user) return res.status(404).json({ error: 'User not found' });
  const balance = parseFloat(user.balance);
  const stakeNum = parseFloat(stake);
  if (stakeNum <= 0) return res.status(400).json({ error: 'Invalid stake' });
  if (balance < stakeNum) return res.status(400).json({ error: 'Insufficient balance' });

  // compute potential return (decimal odds)
  const potentialReturn = stakeNum * parseFloat(odds.price);

  await query('BEGIN');
  try {
    // deduct balance
    await query('UPDATE users SET balance = balance - $1 WHERE id=$2', [stakeNum, userId]);
    // create bet
    const betRes = await query(
      'INSERT INTO bets (user_id, market_id, odds_id, stake, potential_return) VALUES ($1,$2,$3,$4,$5) RETURNING *',
      [userId, odds.market_id, odds_id, stakeNum, potentialReturn]
    );
    await query('COMMIT');
    res.status(201).json(betRes.rows[0]);
  } catch (err) {
    await query('ROLLBACK');
    throw err;
  }
}

** INSERT WALLET HERE  **


export async function settleBet(req: Request, res: Response) {
  // Admin operation: settle a bet by id
  const { betId, outcome, payout } = req.body;
  if (!betId || typeof payout !== 'boolean') return res.status(400).json({ error: 'Missing fields' });

  // Fetch bet
  const betRes = await query('SELECT * FROM bets WHERE id=$1', [betId]);
  const bet = betRes.rows[0];
  if (!bet) return res.status(404).json({ error: 'Bet not found' });
  if (bet.status !== 'placed') return res.status(400).json({ error: 'Bet not in placed state' });

  await query('BEGIN');
  try {
    if (payout) {
      // pay user
      await query('UPDATE users SET balance = balance + $1 WHERE id=$2', [bet.potential_return, bet.user_id]);
      await query('UPDATE bets SET status=$1, settled_at=now(), result=$2 WHERE id=$3', ['settled', { outcome }, betId]);
    } else {
      // mark lost
      await query('UPDATE bets SET status=$1, settled_at=now(), result=$2 WHERE id=$3', ['settled', { outcome }, betId]);
    }
    await query('COMMIT');
    res.json({ ok: true });
  } catch (err) {
    await query('ROLLBACK');
    throw err;
  }
}
import express from 'express';
import { placeBet, settleBet } from '../controllers/betController';
import { requireAuth, requireRole } from '../middleware/auth';
const router = express.Router();

router.post('/', requireAuth, placeBet); // place bet (user)
router.post('/settle', requireAuth, requireRole('admin'), settleBet); // admin settles

export default router;
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: x402
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres -d x402" --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - name: Use Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20
      - name: Install deps
        run: npm ci
      - name: Wait for Postgres
        run: sleep 10
      - name: Run migrations
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/x402
        run: |
          psql $DATABASE_URL -f src/db/migrations/create_schema.sql || true
      - name: Run tests
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/x402
          JWT_SECRET: test-secret
        run: npm test --silent

## API Endpoints (examples)
- POST /api/auth/register { username, email, password }
- POST /api/auth/login { username, password } -> { token }
- GET /api/events
- POST /api/events (admin)
- POST /api/markets (admin)
- POST /api/markets/odds (admin)
- POST /api/bets (user) { odds_id, stake }
- POST /api/bets/settle (admin) { betId, outcome, payout: boolean }

## Notes
- This is a **starter**. You must add: rate-limiting, precise validation, auditing, KYC, anti-fraud, transaction logs, fiat/crypto integrations, SSL, regulatory compliance, and responsible gambling features before production.
- All money values use `NUMERIC` in PG; consider integrating a ledger system for production-grade accounting.

## Responsible gambling & legal
Betting is regulated in many jurisdictions. Use this repo only for lawful purposes and get legal/compliance signoff for your markets and region.



## 📚 **Learn More**

*   **[Specification](spec/v0.1/spec.md)**: The complete technical specification for the x402 extension.
*   **[Python Library](python/x402_a2a/README.md)**: The documentation for the Python implementation of the x402 extension.
*   **[Python Examples](python/examples/)**: The directory containing demonstration applications for the Python implementation.
*   **[A2A Protocol](https://github.com/a2aproject/a2a-python)**: The core agent-to-agent protocol.
*   **[x402 Protocol](https://x402.gitbook.io/x402)**: The underlying payment protocol.

## 🤝 **Contributing**

Contributions are welcome! Please read the [specification](spec/v0.1/spec.md) and the existing code to understand the project's design and goals. Then, feel free to open a pull request with your changes.
