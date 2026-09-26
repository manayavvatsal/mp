import json, glob
from app.engine import compose

def load():
 cats={}
 for f in glob.glob('dataset/categories/*.json'):
  x=json.load(open(f)); cats[x['slug']]=x
 ms={x['merchant_id']:x for x in json.load(open('dataset/merchants_seed.json'))['merchants']}
 cs={x['customer_id']:x for x in json.load(open('dataset/customers_seed.json'))['customers']}
 ts=json.load(open('dataset/triggers_seed.json'))['triggers']
 return cats,ms,cs,ts

def test_all_seed_triggers_have_valid_composition():
 cats,ms,cs,ts=load()
 for t in ts:
  m=ms[t['merchant_id']]; c=cs.get(t.get('customer_id')); x=compose(cats[m['category_slug']],m,t,c)
  assert set(['body','cta','send_as','suppression_key','rationale']) <= set(x)
  assert x['body'].strip()
  assert x['send_as'] in {'vera','merchant_on_behalf'}
  assert 'http://' not in x['body'] and 'https://' not in x['body']

def test_customer_scope_uses_merchant_on_behalf():
 cats,ms,cs,ts=load(); t=next(x for x in ts if x['scope']=='customer'); m=ms[t['merchant_id']]; c=cs[t['customer_id']]
 x=compose(cats[m['category_slug']],m,t,c)
 assert x['send_as']=='merchant_on_behalf'

def test_research_uses_source_and_merchant_signal():
 cats,ms,cs,ts=load(); t=ts[0]; m=ms[t['merchant_id']]
 x=compose(cats[m['category_slug']],m,t,None)
 assert 'JIDA' in x['body'] and '124' in x['body']
