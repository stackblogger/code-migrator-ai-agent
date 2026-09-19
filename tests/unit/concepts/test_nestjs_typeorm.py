from migrator.adapters.frameworks.nestjs import NestJsAdapter
from migrator.adapters.frameworks.typeorm import TypeOrmAdapter
from migrator.concepts.models import ConceptKind
from tests.unit.concepts.helpers import by_key, extract

CONTROLLER = """
import { Controller, Get, Post, Body, HttpCode, UseGuards, HttpException } from '@nestjs/common';
import { ItemDto } from './item.dto';

@Controller({ path: 'items' })
export class ItemsController {
  @Get() list() {}

  @UseGuards(AdminGuard)
  @Post(':id/archive')
  @HttpCode(204)
  archive() { throw new HttpException('gone', 410); }

  @Post()
  create(@Body() dto: ItemDto) { throw new NotFoundException(); }

  helper() { throw new HttpException('x', someStatus); }
}
"""
DTO = """
export class ItemDto {
  @IsString() @MaxLength(50) name!: string;
  @IsOptional() @IsInt() @Min(1) count?: number;
  @MinLength(3) code!: string;
}
"""


def test_routes_status_guards_and_body(make_repo):
    result = extract(
        make_repo, NestJsAdapter(), {"items.controller.ts": CONTROLLER, "item.dto.ts": DTO}
    )
    routes = by_key(result, ConceptKind.ROUTE)
    assert routes["GET /items"]["status"] == 200 and routes["GET /items"]["auth"] is False
    archive = routes["POST /items/{}/archive"]
    assert (archive["status"], archive["auth"], archive["guards"]) == (204, True, ["AdminGuard"])
    assert archive["path"] == "/items/{id}/archive"
    assert routes["POST /items"]["status"] == 201 and routes["POST /items"]["body"] == "ItemDto"


def test_dto_constraints(make_repo):
    result = extract(
        make_repo, NestJsAdapter(), {"items.controller.ts": CONTROLLER, "item.dto.ts": DTO}
    )
    fields = by_key(result, ConceptKind.INPUT_FIELD)
    assert fields["POST /items body.name"] == {
        "constraints": ["max_length=50", "string"],
        "required": True,
    }
    assert fields["POST /items body.count"] == {"constraints": ["int", "min=1"], "required": False}
    assert fields["POST /items body.code"]["constraints"] == ["min_length=3", "string"]


def test_errors_and_unknown_status_note(make_repo):
    result = extract(
        make_repo, NestJsAdapter(), {"items.controller.ts": CONTROLLER, "item.dto.ts": DTO}
    )
    assert set(by_key(result, ConceptKind.ERROR)) == {"HTTP 410", "HTTP 404"}
    assert any("unknown status" in note for note in result.notes)


def test_missing_dto_is_a_note(make_repo):
    result = extract(make_repo, NestJsAdapter(), {"items.controller.ts": CONTROLLER})
    assert any("'ItemDto'" in note and "not found" in note for note in result.notes)


ENTITIES = {
    "author.entity.ts": """
@Entity('authors')
export class Author {
  @PrimaryGeneratedColumn('uuid') id!: string;
  @Column({ unique: true, name: 'full_name' }) fullName!: string;
  @Column('text', { nullable: true }) bio!: string | null;
  @OneToMany(() => Book, (b) => b.author) books!: Book[];
}
""",
    "book.entity.ts": """
@Entity()
export class Book {
  @PrimaryColumn() isbn!: string;
  @ManyToOne(() => Author, (a) => a.books) author!: Author;
  @ManyToOne(() => Author) @JoinColumn({ name: 'editor_id' }) editor!: Author;
}
""",
}


def test_typeorm_columns(make_repo):
    result = extract(make_repo, TypeOrmAdapter(), ENTITIES)
    columns = by_key(result, ConceptKind.COLUMN)
    assert columns["authors.id"]["primary_key"] is True
    full_name = columns["authors.full_name"]
    assert (full_name["nullable"], full_name["unique"], full_name["primary_key"]) == (
        False,
        True,
        False,
    )
    assert full_name["type"] == "varchar(255)"
    assert columns["authors.id"]["type"] == "uuid"
    assert columns["authors.bio"]["type"] == "text"
    assert columns["authors.bio"]["nullable"] is True
    assert "authors.books" not in columns  # OneToMany has no column
    assert columns["Book.authorId"]["references"] == "authors"
    assert columns["Book.authorId"]["nullable"] is True  # relations are nullable by default
    assert "Book.editor_id" in columns
    assert any("no table name on Book" in note for note in result.notes)
