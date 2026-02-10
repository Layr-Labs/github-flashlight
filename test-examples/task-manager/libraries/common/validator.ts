/**
 * Input validation utilities
 */

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}

export class Validator {
  static isNonEmptyString(value: any, fieldName: string): void {
    if (typeof value !== 'string' || value.trim().length === 0) {
      throw new ValidationError(`${fieldName} must be a non-empty string`);
    }
  }

  static isValidId(value: any): boolean {
    return typeof value === 'string' && /^[a-zA-Z0-9-_]+$/.test(value);
  }

  static requireFields(obj: any, fields: string[]): void {
    for (const field of fields) {
      if (!(field in obj)) {
        throw new ValidationError(`Missing required field: ${field}`);
      }
    }
  }
}
