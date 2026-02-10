import express, { Request, Response, NextFunction } from 'express';
import bodyParser from 'body-parser';
import axios from 'axios';
import { Logger, Validator, ValidationError } from '../../libraries/common';

const app = express();
const PORT = process.env.PORT || 3000;
const AUTH_SERVICE = process.env.AUTH_SERVICE || 'http://localhost:3001';
const DB_SERVICE = process.env.DB_SERVICE || 'http://localhost:3002';
const logger = new Logger('api-service');

app.use(bodyParser.json());

interface Task {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in-progress' | 'completed';
  createdAt: string;
  userId: string;
}

/**
 * Authentication middleware
 * Verifies JWT token with auth service
 */
async function authenticate(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace('Bearer ', '');

  if (!token) {
    logger.warn('Request without authentication token');
    return res.status(401).json({ error: 'Authentication required' });
  }

  try {
    const response = await axios.post(`${AUTH_SERVICE}/auth/verify`, { token });

    if (response.data.valid) {
      (req as any).user = response.data.decoded;
      next();
    } else {
      res.status(401).json({ error: 'Invalid token' });
    }
  } catch (error) {
    logger.error('Auth service error', error as Error);
    res.status(500).json({ error: 'Authentication service unavailable' });
  }
}

/**
 * POST /tasks
 * Creates a new task
 */
app.post('/tasks', authenticate, async (req: Request, res: Response) => {
  try {
    const { title, description } = req.body;
    const userId = (req as any).user.userId;

    Validator.requireFields(req.body, ['title', 'description']);
    Validator.isNonEmptyString(title, 'title');

    const task: Task = {
      id: `task-${Date.now()}`,
      title,
      description,
      status: 'pending',
      createdAt: new Date().toISOString(),
      userId
    };

    // Store in database service
    await axios.post(`${DB_SERVICE}/data`, {
      key: task.id,
      value: task
    });

    logger.info(`Task created: ${task.id}`);
    res.status(201).json(task);
  } catch (error) {
    if (error instanceof ValidationError) {
      res.status(400).json({ error: error.message });
    } else {
      logger.error('Error creating task', error as Error);
      res.status(500).json({ error: 'Failed to create task' });
    }
  }
});

/**
 * GET /tasks
 * Lists all tasks for the authenticated user
 */
app.get('/tasks', authenticate, async (req: Request, res: Response) => {
  try {
    const userId = (req as any).user.userId;

    // Get all keys from database
    const keysResponse = await axios.get(`${DB_SERVICE}/data`);
    const taskKeys = keysResponse.data.keys.filter((k: string) => k.startsWith('task-'));

    // Fetch all tasks
    const tasks: Task[] = [];
    for (const key of taskKeys) {
      const taskResponse = await axios.get(`${DB_SERVICE}/data/${key}`);
      if (taskResponse.data.exists) {
        const task = taskResponse.data.value;
        if (task.userId === userId) {
          tasks.push(task);
        }
      }
    }

    logger.info(`Retrieved ${tasks.length} tasks for user ${userId}`);
    res.json({ tasks, count: tasks.length });
  } catch (error) {
    logger.error('Error listing tasks', error as Error);
    res.status(500).json({ error: 'Failed to list tasks' });
  }
});

/**
 * GET /tasks/:id
 * Gets a specific task
 */
app.get('/tasks/:id', authenticate, async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const userId = (req as any).user.userId;

    const response = await axios.get(`${DB_SERVICE}/data/${id}`);

    if (!response.data.exists) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const task = response.data.value;
    if (task.userId !== userId) {
      return res.status(403).json({ error: 'Access denied' });
    }

    logger.info(`Retrieved task: ${id}`);
    res.json(task);
  } catch (error) {
    logger.error('Error getting task', error as Error);
    res.status(500).json({ error: 'Failed to get task' });
  }
});

/**
 * PUT /tasks/:id
 * Updates a task
 */
app.put('/tasks/:id', authenticate, async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const userId = (req as any).user.userId;
    const updates = req.body;

    // Get existing task
    const response = await axios.get(`${DB_SERVICE}/data/${id}`);
    if (!response.data.exists) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const task = response.data.value;
    if (task.userId !== userId) {
      return res.status(403).json({ error: 'Access denied' });
    }

    // Update task
    const updatedTask = { ...task, ...updates, id, userId };
    await axios.post(`${DB_SERVICE}/data`, {
      key: id,
      value: updatedTask
    });

    logger.info(`Updated task: ${id}`);
    res.json(updatedTask);
  } catch (error) {
    logger.error('Error updating task', error as Error);
    res.status(500).json({ error: 'Failed to update task' });
  }
});

/**
 * DELETE /tasks/:id
 * Deletes a task
 */
app.delete('/tasks/:id', authenticate, async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const userId = (req as any).user.userId;

    // Verify ownership
    const getResponse = await axios.get(`${DB_SERVICE}/data/${id}`);
    if (!getResponse.data.exists) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const task = getResponse.data.value;
    if (task.userId !== userId) {
      return res.status(403).json({ error: 'Access denied' });
    }

    // Delete task
    await axios.delete(`${DB_SERVICE}/data/${id}`);

    logger.info(`Deleted task: ${id}`);
    res.json({ success: true, deleted: true });
  } catch (error) {
    logger.error('Error deleting task', error as Error);
    res.status(500).json({ error: 'Failed to delete task' });
  }
});

app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy', service: 'api' });
});

app.listen(PORT, () => {
  logger.info(`API service listening on port ${PORT}`);
});
