import pytest
from mobileflow.ui_tree import compress_page_source, _parse_nodes


class TestUiTree:
    
    def test_normal_xml_compression_format(self):
        """1) 正常 XML 压缩输出格式"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
    <node bounds="[0,0][300,500]" text="微信" content-desc="" clickable="true" resource-id="com.tencent.mm:id/title" class="android.widget.TextView"/>
    <node bounds="[0,600][360,800]" text="" content-desc="设置" clickable="false" resource-id="com.tencent.mm:id/settings_btn" class="android.widget.Button"/>
</hierarchy>'''
        result = compress_page_source(xml, max_elements=60)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        # 验证第一行格式：[0] 「微信」 (resource-id 短名) {可点} bounds
        assert lines[0] == "[0] 「微信」 (title) {可点} [0,0][300,500]"
        # 第二行：无 text 用 content-desc；clickable=false 不输出可点标记
        assert lines[1] == "[1] 「设置」 (settings_btn) [0,600][360,800]"

    def test_empty_xml_returns_empty(self):
        """2) 空 XML 返回（空屏幕）"""
        xml = '<?xml version="1.0" encoding="UTF-8"?><hierarchy></hierarchy>'
        result = compress_page_source(xml, max_elements=60)
        assert result == "（空屏幕）"

    def test_truncate_when_exceeding_max_elements(self):
        """3) 超过 max_elements 截断"""
        nodes = ""
        for i in range(70):
            nodes += f'<node bounds="[0,{i}][100,{i+10}]" text="btn_{i}" content-desc="" clickable="true" class="android.widget.Button"/>'
        xml = f'<?xml version="1.0" encoding="UTF-8"?><hierarchy>{nodes}</hierarchy>'
        result = compress_page_source(xml, max_elements=60)
        lines = result.strip().split("\n")
        # 60 个节点 + 1 行截断提示
        assert len(lines) == 61
        # 第一行索引 [0]
        assert lines[0].startswith("[0] 「btn_0」")
        # 第 60 行索引 [59]
        assert lines[59].startswith("[59] 「btn_59」")
        # 末尾是截断提示
        assert lines[-1] == "...（还有 10 个元素未显示）"

    def test_special_characters_escaping(self):
        """4) 特殊字符转义"""
        # text 中包含换行符、引号等特殊字符
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
    <node bounds="[0,0][100,100]" text="line1\nline2" content-desc="" clickable="true" class="android.widget.TextView"/>
</hierarchy>'''
        result = compress_page_source(xml, max_elements=60)
        assert "「line1\\nline2」" in result or "「line1\nline2」" in result
        # 验证不会崩溃且包含节点
        assert result.strip().startswith("[0]")

    def test_node_with_only_content_desc(self):
        """5) 无 text 只有 content-desc 的节点"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
    <node bounds="[10,10][200,200]" text="" content-desc="搜索" clickable="true" resource-id="com.example.app:id/search_icon" class="android.widget.EditText"/>
</hierarchy>'''
        result = compress_page_source(xml, max_elements=60)
        assert result.strip() == "[0] 「搜索」 (search_icon) {可点} [10,10][200,200]"

    def test_parse_nodes_returns_list(self):
        """_parse_nodes 返回节点列表且结构正确"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
    <node bounds="[0,0][100,100]" text="OK" content-desc="" clickable="true" class="android.widget.Button"/>
</hierarchy>'''
        nodes = _parse_nodes(xml)
        assert isinstance(nodes, list)
        assert len(nodes) == 1
        node = nodes[0]
        assert node["text"] == "OK"
        assert node["content-desc"] == ""
        assert node["clickable"] == "true"
        assert node["bounds"] == "[0,0][100,100]"
        assert node["class"] == "android.widget.Button"

    def test_parse_nodes_empty_xml(self):
        """_parse_nodes 处理空 XML"""
        xml = '<?xml version="1.0" encoding="UTF-8"?><hierarchy></hierarchy>'
        nodes = _parse_nodes(xml)
        assert isinstance(nodes, list)
        assert len(nodes) == 0

    def test_parse_nodes_returns_all_nodes(self):
        """_parse_nodes 不截断：返回全部节点（截断由 compress_page_source 负责）"""
        nodes_xml = ""
        for i in range(80):
            nodes_xml += f'<node bounds="[0,{i}][50,{i+5}]" text="item_{i}" content-desc="" clickable="false" class="android.widget.TextView"/>'
        xml = f'<?xml version="1.0" encoding="UTF-8"?><hierarchy>{nodes_xml}</hierarchy>'
        nodes = _parse_nodes(xml)
        assert len(nodes) == 80
        assert nodes[0]["text"] == "item_0"
        assert nodes[-1]["text"] == "item_79"
