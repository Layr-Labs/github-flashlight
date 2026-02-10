import express, { Request, Response } from 'express';
import bodyParser from 'body-parser';
import { Logger } from '../../libraries/common';

const app = express();
const PORT = process.env.PORT || 3002;
const logger = new Logger('database-service');

app.use(bodyParser.json());

// In-memory key-value store
const dataStore = new Map<string, any>();

/**
 * GET /data/:key
 * Retrieves value for given key
 */
app.get('/data/:key', (req: Request, res: Response) => {
  const { key } = req.params;

  logger.debug(`GET request for key: ${key}`);

  if (dataStore.has(key)) {
    const value = dataStore.get(key);
    logger.info(`Retrieved key: ${key}`);
    res.json({ key, value, exists: true });
  } else {
    logger.warn(`Key not found: ${key}`);
    res.status(404).json({ error: 'Key not found', exists: false });
  }
});

/**
 * POST /data
 * Stores key-value pair
 */
app.post('/data', (req: Request, res: Response) => {
  const { key, value } = req.body;

  if (!key) {
    return res.status(400).json({ error: 'Key is required' });
  }

  const existed = dataStore.has(key);
  dataStore.set(key, value);

  logger.info(`Stored key: ${key} (${existed ? 'updated' : 'created'})`);
  res.json({
    success: true,
    key,
    operation: existed ? 'updated' : 'created'
  });
});

/**
 * DELETE /data/:key
 * Deletes key-value pair
 */
app.delete('/data/:key', (req: Request, res: Response) => {
  const { key } = req.params;

  if (dataStore.has(key)) {
    dataStore.delete(key);
    logger.info(`Deleted key: ${key}`);
    res.json({ success: true, deleted: true });
  } else {
    logger.warn(`Attempted to delete non-existent key: ${key}`);
    res.status(404).json({ error: 'Key not found', deleted: false });
  }
});

/**
 * GET /data
 * Lists all keys
 */
app.get('/data', (req: Request, res: Response) => {
  const keys = Array.from(dataStore.keys());
  logger.debug(`Listed ${keys.length} keys`);
  res.json({ keys, count: keys.length });
});

app.get('/health', (req: Request, res: Response) => {
  res.json({
    status: 'healthy',
    service: 'database',
    itemCount: dataStore.size
  });
});

app.listen(PORT, () => {
  logger.info(`Database service listening on port ${PORT}`);
});
