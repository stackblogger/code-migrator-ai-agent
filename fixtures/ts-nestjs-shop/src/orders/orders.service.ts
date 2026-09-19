import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { UsersService } from '../users/users.service';
import { CreateOrderDto } from './dto/create-order.dto';
import { Order, OrderStatus } from './order.entity';

@Injectable()
export class OrdersService {
  constructor(
    @InjectRepository(Order) private readonly orders: Repository<Order>,
    private readonly users: UsersService,
  ) {}

  async create(userId: number, dto: CreateOrderDto): Promise<Order> {
    if (Number(dto.total) <= 0) {
      throw new BadRequestException('Total must be greater than zero');
    }
    const user = await this.users.findById(userId);
    const order = this.orders.create({ user, total: dto.total, note: dto.note ?? null });
    return this.orders.save(order);
  }

  async listForUser(userId: number): Promise<Order[]> {
    return this.orders.find({
      where: { user: { id: userId } },
      order: { createdAt: 'DESC' },
    });
  }

  async cancel(userId: number, orderId: number): Promise<Order> {
    const order = await this.orders.findOne({ where: { id: orderId, user: { id: userId } } });
    if (!order) {
      throw new NotFoundException(`Order ${orderId} not found`);
    }
    if (order.status === OrderStatus.Paid) {
      throw new BadRequestException('Paid orders cannot be cancelled');
    }
    order.status = OrderStatus.Cancelled;
    return this.orders.save(order);
  }
}
