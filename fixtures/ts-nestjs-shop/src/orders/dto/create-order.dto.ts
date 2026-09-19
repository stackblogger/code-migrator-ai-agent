import { IsNumberString, IsOptional, IsString, MaxLength } from 'class-validator';

export class CreateOrderDto {
  @IsNumberString()
  total!: string;

  @IsOptional()
  @IsString()
  @MaxLength(200)
  note?: string;
}
