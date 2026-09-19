from migrator.adapters.languages.typescript.parser import parse_typescript

SOURCE = b"""
import 'reflect-metadata';
import type { User } from '../users/user.entity';
import Default, { A as B, C } from './things';
import * as path from 'path';
export { helper } from './helpers';

@Controller('orders')
export class OrdersController {
  @Column() total!: string;
  constructor(private readonly svc: Service) {}
  @Get(':id')
  findOne(@Param('id') id: string) { return process.env.API_KEY; }
}

@Injectable()
class Hidden {}

export interface Payload { sub: number }
export enum Status { A = 'a' }
export type Id = number;
export const handler = () => process.env['OTHER_KEY'];
const LIMIT = 10;
export function top() {}
"""


def parse():
    return parse_typescript("src/orders/orders.controller.ts", SOURCE)


def test_imports():
    imports = {i.module: i for i in parse().imports}
    assert set(imports) == {
        "reflect-metadata",
        "../users/user.entity",
        "./things",
        "path",
        "./helpers",
    }
    assert imports["../users/user.entity"].type_only is True
    assert imports["./things"].names == ["Default", "A", "C"]
    assert imports["path"].names == ["*"]
    assert imports["./helpers"].names == ["helper"]


def test_symbols_and_decorators():
    symbols = {(s.parent, s.name): s for s in parse().symbols}
    controller = symbols[(None, "OrdersController")]
    assert controller.kind == "class"
    assert controller.decorators == ["Controller"]
    assert controller.exported is True

    assert symbols[("OrdersController", "findOne")].decorators == ["Get"]
    assert symbols[("OrdersController", "total")].kind == "field"
    assert symbols[("OrdersController", "total")].decorators == ["Column"]
    assert symbols[(None, "Hidden")].decorators == ["Injectable"]
    assert symbols[(None, "Hidden")].exported is False

    kinds = {name: s.kind for (parent, name), s in symbols.items() if parent is None}
    assert kinds["Payload"] == "interface"
    assert kinds["Status"] == "enum"
    assert kinds["Id"] == "type"
    assert kinds["handler"] == "function"
    assert kinds["LIMIT"] == "variable"
    assert kinds["top"] == "function"


def test_env_vars():
    assert parse().env_vars == ["API_KEY", "OTHER_KEY"]


def test_syntax_error_is_flagged():
    assert parse_typescript("bad.ts", b"class {{{").parse_errors is True
