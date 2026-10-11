import csv
import io
def cells(row, columns, consumer):
    def render(value):
        if value is None:return ''
        if value is True:return 'true'
        if value is False:return 'false'
        return str(value)
    return [render(row.get(c['key'])) for c in columns]


def export(payload, config):
    columns=payload.get('columns');rows=payload.get('rows')
    if not isinstance(columns,list) or not columns or not isinstance(rows,list):
        raise ValueError('columns and rows required')
    if any(not isinstance(c,dict) or not isinstance(c.get('key'),str) or not isinstance(c.get('label'),str) for c in columns) or any(not isinstance(r,dict) for r in rows):
        raise ValueError('invalid records')
    stream=io.StringIO(newline='')
    writer=csv.writer(stream,delimiter=config['delimiter'],lineterminator='\r\n')
    writer.writerow([c['label'] for c in columns])
    for row in rows:writer.writerow(cells(row,columns,config['consumer']))
    data=stream.getvalue().encode('utf-8')
    return (b'\xef\xbb\xbf' if config['bom'] else b'')+data
