from app.dic_validator import validate_dic_content


def test_valid_content():
    text = "# comment\nHello = Привет, GREETING, it, first word\nWorld = Мир\n"
    errors, count = validate_dic_content(text)
    assert errors == []
    assert count == 2


def test_empty_content():
    errors, count = validate_dic_content("# only comments\n\n")
    assert errors
    assert count == 0


def test_duplicate_source():
    text = "Hello = Привет\nhello = Здравствуй\n"
    errors, count = validate_dic_content(text)
    assert any("Повторяющиеся" in e for e in errors)


def test_missing_equals():
    errors, count = validate_dic_content("Hello Привет\n")
    assert any("не соответствует формату" in e for e in errors)


def test_empty_target():
    # запятая после "=" делает \S+ формально валидным, но CSV-разбор даёт
    # пустое первое поле — это и есть кейс "пустой target"
    errors, count = validate_dic_content("Hello = ,note\n")
    assert any("пустой source или target" in e for e in errors)


def test_missing_target_entirely():
    # "Hello =" без непробельного символа после "=" не проходит даже
    # первый паттерн — та же грамматика, что и в родительском проекте
    errors, count = validate_dic_content("Hello =\n")
    assert any("не соответствует формату" in e for e in errors)
