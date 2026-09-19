import { Body, Controller, Get, Param, ParseIntPipe, Post, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { CreateUserDto } from './dto/create-user.dto';
import { UsersService } from './users.service';

@Controller('users')
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @Post()
  async register(@Body() dto: CreateUserDto) {
    const user = await this.users.create(dto);
    return { id: user.id, email: user.email, role: user.role, createdAt: user.createdAt };
  }

  @UseGuards(JwtAuthGuard)
  @Get(':id')
  async findOne(@Param('id', ParseIntPipe) id: number) {
    const user = await this.users.findById(id);
    return { id: user.id, email: user.email, role: user.role, createdAt: user.createdAt };
  }
}
