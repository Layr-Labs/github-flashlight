/**
 * Shared logging utility used across all services
 */

export enum LogLevel {
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
  DEBUG = 'DEBUG'
}

export class Logger {
  constructor(private serviceName: string) {}

  private formatMessage(level: LogLevel, message: string): string {
    const timestamp = new Date().toISOString();
    return `[${timestamp}] [${this.serviceName}] [${level}] ${message}`;
  }

  info(message: string): void {
    console.log(this.formatMessage(LogLevel.INFO, message));
  }

  warn(message: string): void {
    console.warn(this.formatMessage(LogLevel.WARN, message));
  }

  error(message: string, error?: Error): void {
    const errorMsg = error ? `${message}: ${error.message}` : message;
    console.error(this.formatMessage(LogLevel.ERROR, errorMsg));
  }

  debug(message: string): void {
    if (process.env.DEBUG === 'true') {
      console.log(this.formatMessage(LogLevel.DEBUG, message));
    }
  }
}
