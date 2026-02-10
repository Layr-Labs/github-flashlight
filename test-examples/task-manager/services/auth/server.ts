import express, { Request, Response } from 'express';
import bodyParser from 'body-parser';
import jwt from 'jsonwebtoken';
import { Logger } from '../../libraries/common';

const app = express();
const PORT = process.env.PORT || 3001;
const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-key';
const logger = new Logger('auth-service');

app.use(bodyParser.json());

// Mock user database
const users = new Map<string, { password: string; userId: string }>([
  ['admin', { password: 'admin123', userId: 'user-001' }],
  ['user', { password: 'user123', userId: 'user-002' }]
]);

/**
 * POST /auth/login
 * Authenticates user and returns JWT token
 */
app.post('/auth/login', (req: Request, res: Response) => {
  const { username, password } = req.body;

  logger.info(`Login attempt for user: ${username}`);

  if (!username || !password) {
    logger.warn('Missing username or password');
    return res.status(400).json({ error: 'Username and password required' });
  }

  const user = users.get(username);
  if (!user || user.password !== password) {
    logger.warn(`Failed login for user: ${username}`);
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  const token = jwt.sign(
    { userId: user.userId, username },
    JWT_SECRET,
    { expiresIn: '24h' }
  );

  logger.info(`Successful login for user: ${username}`);
  res.json({ token, userId: user.userId });
});

/**
 * POST /auth/verify
 * Verifies JWT token validity
 */
app.post('/auth/verify', (req: Request, res: Response) => {
  const { token } = req.body;

  if (!token) {
    return res.status(400).json({ error: 'Token required' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    logger.debug(`Token verified for user: ${(decoded as any).username}`);
    res.json({ valid: true, decoded });
  } catch (error) {
    logger.warn('Invalid token verification attempt');
    res.status(401).json({ valid: false, error: 'Invalid or expired token' });
  }
});

app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy', service: 'auth' });
});

app.listen(PORT, () => {
  logger.info(`Auth service listening on port ${PORT}`);
});
