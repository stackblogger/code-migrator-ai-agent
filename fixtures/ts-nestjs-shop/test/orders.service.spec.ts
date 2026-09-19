import { BadRequestException } from '@nestjs/common';
import { OrdersService } from '../src/orders/orders.service';
import { OrderStatus } from '../src/orders/order.entity';

describe('OrdersService', () => {
  const orders = {
    create: jest.fn((data) => data),
    save: jest.fn(async (data) => ({ id: 1, ...data })),
    findOne: jest.fn(),
  };
  const users = { findById: jest.fn(async (id: number) => ({ id })) };
  const service = new OrdersService(orders as any, users as any);

  it('rejects zero total', async () => {
    await expect(service.create(1, { total: '0' })).rejects.toBeInstanceOf(BadRequestException);
  });

  it('creates an order for the user', async () => {
    const order = await service.create(1, { total: '19.99' });
    expect(order.total).toBe('19.99');
    expect(order.note).toBeNull();
  });

  it('does not cancel paid orders', async () => {
    orders.findOne.mockResolvedValueOnce({ id: 2, status: OrderStatus.Paid });
    await expect(service.cancel(1, 2)).rejects.toBeInstanceOf(BadRequestException);
  });
});
