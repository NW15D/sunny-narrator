from bs4 import BeautifulSoup

def rem_tags(xml_string):
    #Заглушка
    return xml_string  # Если тега body нет, возвращаем исходную строку
    # Создаем объект BeautifulSoup с парсером 'html.parser'
    soup = BeautifulSoup(xml_string, 'lxml')
    # Находим тег body
    body_tag = soup.find('body')

    if not body_tag:
        return str(soup)  # Если тега body нет, возвращаем исходную строку

    # Список тегов для проверки
    tags_to_check = ['section', 'p']

    def process_tag(tag, parent):
        # Рекурсивная функция обработки тегов
        children = list(tag.children)

        for i in range(len(children)):
            child = children[i]

            if child.name in tags_to_check:
                next_child = None
                if i + 1 < len(children):
                    next_child = children[i + 1]

                # Если следующий элемент тоже тег из списка, заменяем текущий на закрывающий и открывающийся
                if next_child and next_child.name == child.name:

                    new_tag = soup.new_tag(child.name)
                    closing_tag = soup.new_string(f'</{child.name}>')
                    opening_tag = soup.new_string(f'<{child.name}>')

                    # Заменяем текущий тег на закрывающий и новый открывающийся
                    tag.insert(i + 1, new_tag)
                    tag.insert(i, closing_tag)
                    process_tag(new_tag, parent)  # Рекурсивно обрабатываем вложенные элементы
                else:
                    process_tag(child, child)  # Рекурсивно обрабатываем дочерние элементы


    for tag_name in tags_to_check:
        # Находим все теги текущего типа на первом уровне внутри body
        open_tags = body_tag.find_all(tag_name, recursive=False)

        for tag in open_tags:
            process_tag(tag, tag)


    # Fix unclosed tags
    for tag_name in tags_to_check:
        tags = body_tag.find_all(tag_name)
        for tag in tags:
            if not tag.find_next_sibling(tag_name):
                closing_tag = soup.new_string(f'</{tag_name}>')
                tag.insert_after(closing_tag)

    # Fix missing opening tags
    for tag_name in tags_to_check:
        tags = body_tag.find_all(tag_name)
        for tag in tags:
            if not tag.find_previous_sibling(tag_name):
                opening_tag = soup.new_string(f'<{tag_name}>')
                tag.insert_before(opening_tag)

    return str(soup).replace('<?xml version="1.0" encoding="utf-8"?>', '').strip()


