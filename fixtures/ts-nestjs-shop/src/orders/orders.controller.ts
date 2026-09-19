import { Body, Controller, Get, Param, ParseIntPipe, Post, Req, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import type { TokenPayload } from '../auth/auth.service';
import { CreateOrderDto } from './dto/create-order.dto';
import { Order } from './order.entity';
import { OrdersService } from './orders.service';

function toResponse(order: Order) {
  return {
    id: order.id,
    total: order.total,
    status: order.status,
    note: order.note,
    createdAt: order.createdAt,
  };
}

@UseGuards(JwtAuthGuard)
@Controller('orders')
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Post()
  async create(@Req() req: { user: TokenPayload }, @Body() dto: CreateOrderDto) {
    return toResponse(await this.orders.create(Number(req.user.sub), dto));
  }

  @Get()
  async list(@Req() req: { user: TokenPayload }) {
    const orders = await this.orders.listForUser(Number(req.user.sub));
    return orders.map(toResponse);
  }

  @Post(':id/cancel')
  async cancel(@Req() req: { user: TokenPayload }, @Param('id', ParseIntPipe) id: number) {
    return toResponse(await this.orders.cancel(Number(req.user.sub), id));
  }
}
