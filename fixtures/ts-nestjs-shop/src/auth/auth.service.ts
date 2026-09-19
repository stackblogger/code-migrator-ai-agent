import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { createHash } from 'crypto';
import type { User } from '../users/user.entity';

export interface TokenPayload {
  sub: string; // JWT standard says `sub` is a string
  role: string;
}

@Injectable()
export class AuthService {
  constructor(private readonly jwt: JwtService) {}

  hashPassword(password: string): string {
    return createHash('sha256').update(password).digest('hex');
  }

  issueToken(user: User): string {
    return this.jwt.sign({ sub: String(user.id), role: user.role });
  }

  verifyToken(token: string): TokenPayload {
    try {
      return this.jwt.verify<TokenPayload>(token);
    } catch {
      throw new UnauthorizedException('Invalid token');
    }
  }
}
