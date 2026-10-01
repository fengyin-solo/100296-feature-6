from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def show(title, r):
    data = r.json()
    print(f"--- {title}: HTTP {r.status_code} ok={data.get('ok')}")
    print("   ", data.get('message') or data)


# 0. 初始统计：已登记 1 台(REGI-0002)
stats = c.get('/api/register/stats').json()
print("初始 stats:", stats)
assert stats['在用台数'] == 1, stats
ov = c.get('/api/overview').json()
print("概览卡片:", ov['cards'])
assert next(x for x in ov['cards'] if x['label'] == '在用台数')['value'] == 1

# 1. 缺登记证号与使用单位 -> 点名
r = c.post('/api/register', json={'values': {'设备编号': 'T-1', '设备名称': 'n', '设备种类': 'k'}})
show('缺使用单位+登记证号', r)
assert r.json()['ok'] is False
assert '使用单位' in r.json()['message'] and '登记证号' in r.json()['message']

# 2. 正常提交 -> 待登记
r = c.post('/api/register', json={'values': {
    '设备编号': 'T-1', '设备名称': '测试吊', '设备种类': '起重机械',
    '使用单位': '甲公司', '安装地点': 'A区', '投用日期': '2026-10-01',
    '登记证号': 'ZZ-1', 'operator': '张三'}})
show('提交登记', r)
assert r.json()['ok'] and r.json()['entry']['status'] == '待登记'
new_id = r.json()['entry']['id']

# 3. 待登记直接申请停用 -> 退回
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请停用', 'operator': '李四'}})
show('跳步：待登记→停用', r)
assert r.json()['ok'] is False and '办理登记' in r.json()['message']

# 4. 待登记直接注销 -> 退回
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请注销'}})
show('跳步：待登记→注销', r)
assert r.json()['ok'] is False

# 5. 办理登记 -> 已登记，留痕（时间+经手人）
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '办理登记', 'operator': '王五'}})
show('办理登记', r)
assert r.json()['ok'] and r.json()['entry']['status'] == '已登记'
detail = c.get(f'/api/register/{new_id}').json()
records = detail['流转记录']
assert len(records) == 2
assert records[-1]['经手人'] == '王五'
assert records[-1]['变更前'] == '待登记' and records[-1]['变更后'] == '已登记'
print('流转留痕:', records)

# 6. 已登记直接注销 -> 退回，须先停用
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请注销'}})
show('跳步：已登记→注销', r)
assert r.json()['ok'] is False and '停用' in r.json()['message']

# 7. 已登记再办理登记 -> 动作不被允许
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '办理登记'}})
show('重复办理登记', r)
assert r.json()['ok'] is False

# 8. 申请停用 -> 停用中；在用台数随之减少
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请停用', 'operator': '赵六'}})
show('申请停用', r)
assert r.json()['entry']['status'] == '停用中'
stats = c.get('/api/register/stats').json()
assert stats['在用台数'] == 1 and stats['停用中'] == 2, stats  # REGI-0002 在用；REGI-0003+T-1 停用
ov = c.get('/api/overview').json()
assert next(x for x in ov['cards'] if x['label'] == '在用台数')['value'] == 1

# 9. 停用中再申请停用 -> 退回并提示解停
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请停用'}})
show('停用中再停用', r)
assert r.json()['ok'] is False and '解停恢复' in r.json()['message']

# 10. 解停恢复 -> 已登记
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '解停恢复', 'operator': '孙七'}})
show('解停恢复', r)
assert r.json()['entry']['status'] == '已登记'
stats = c.get('/api/register/stats').json()
assert stats['在用台数'] == 2, stats

# 11. 再停用 -> 注销 -> 终态
c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请停用'}})
r = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': '申请注销', 'operator': '周八'}})
show('申请注销', r)
assert r.json()['entry']['status'] == '已注销'
for act in ['办理登记', '申请停用', '解停恢复', '申请注销']:
    resp = c.post(f'/api/register/{new_id}/actions', json={'values': {'action': act}})
    assert resp.json()['ok'] is False, (act, resp.json())
    print(f'已注销执行{act} ->', resp.json()['message'])

# 12. 种子里已注销的 REGI-0004 同样终态
resp = c.post('/api/register/4/actions', json={'values': {'action': '解停恢复'}})
assert resp.json()['ok'] is False and '终态' in resp.json()['message']

# 13. 重复提交同一设备编号：不新增、不覆盖，追加备注
before = c.get('/api/register/2').json()
r = c.post('/api/register', json={'values': {
    '设备编号': 'REGI-0002', '设备名称': before['设备名称'], '设备种类': '起重机械',
    '使用单位': before['使用单位'], '安装地点': '二号厂房跨间（已改编号牌）',
    '投用日期': before['投用日期'], '登记证号': before['登记证号'], 'operator': '复查员'},
    'remark': '班组复查时重复登记'})
show('重复提交登记', r)
assert r.json()['ok'] is True
after = c.get('/api/register/2').json()
assert after['id'] == 2
assert after['设备名称'] == before['设备名称'] and after['登记证号'] == before['登记证号']
assert '复查员' in after['重复登记备注'] and '班组复查' in after['重复登记备注']
assert len(after['流转记录']) == len(before['流转记录']) + 1
print('追加的备注:\n', after['重复登记备注'])
total = c.get('/api/register?size=200').json()['total']
assert total == 5, total  # 4 条种子 + T-1，重复未新增

# 14. 非法动作
r = c.post('/api/register/2/actions', json={'values': {'action': '随便改'}})
assert r.json()['ok'] is False

# 15. 过滤仍然可用
assert c.get('/api/register', params={'status': '已注销'}).json()['total'] == 2
print('\n全部断言通过 ✅')
