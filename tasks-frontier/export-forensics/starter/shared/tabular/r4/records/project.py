def text(value):
    if value is None:return ''
    if value is True:return 'true'
    if value is False:return 'false'
    return str(value)


def cells(row, columns, consumer):
    values=[row.get(column['key']) for column in columns]
    # r4 consolidated the sparse and interactive paths.
    return [text(value) for value in values if value]
