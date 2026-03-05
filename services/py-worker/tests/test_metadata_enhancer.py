"""测试元数据增强器"""

from worker.chunking import DocType
from worker.metadata_enhancer import EnhancedMetadata, MetadataEnhancer


def test_extract_keywords_basic() -> None:
    """测试基础关键词提取"""
    enhancer = MetadataEnhancer(max_keywords=5)
    text = """
    Machine learning is a subset of artificial intelligence that focuses on 
    developing algorithms that allow computers to learn from data without being 
    explicitly programmed. Machine learning models can identify patterns in data 
    and make predictions or decisions based on those patterns.
    """
    keywords = enhancer._extract_keywords(text)
    
    assert len(keywords) <= 5
    assert "machine" in keywords or "learning" in keywords
    assert "patterns" in keywords or "data" in keywords


def test_extract_keywords_chinese() -> None:
    """测试中文关键词提取"""
    enhancer = MetadataEnhancer(max_keywords=5)
    text = """
    机器学习是人工智能的一个分支，它专注于开发算法，
    使计算机能够从数据中学习而无需明确编程。
    机器学习模型可以识别数据中的模式并做出预测。
    """
    keywords = enhancer._extract_keywords(text)
    
    assert len(keywords) <= 5
    assert len(keywords) > 0


def test_classify_document_code() -> None:
    """测试代码文档分类"""
    enhancer = MetadataEnhancer()
    text = """
    def calculate_sum(numbers):
        total = 0
        for num in numbers:
            total += num
        return total
    
    class Calculator:
        def __init__(self):
            self.value = 0
        
        def add(self, x):
            self.value += x
    """
    doc_type = enhancer._classify_document(text)
    assert doc_type == DocType.CODE


def test_classify_document_technical() -> None:
    """测试技术文档分类"""
    enhancer = MetadataEnhancer()
    text = """
    API Authentication Guide
    
    This document describes how to authenticate with our API endpoint.
    The server uses JSON tokens for authentication and authorization.
    You need to configure your client with the proper credentials.
    """
    doc_type = enhancer._classify_document(text)
    assert doc_type == DocType.TECHNICAL


def test_classify_document_conversational() -> None:
    """测试对话式文档分类"""
    enhancer = MetadataEnhancer()
    text = """
    你好，请问如何使用这个 API？
    
    谢谢你的提问！让我来帮助你。
    
    请问还有其他问题吗？
    """
    doc_type = enhancer._classify_document(text)
    assert doc_type == DocType.CONVERSATIONAL


def test_classify_document_general() -> None:
    """测试通用文档分类"""
    enhancer = MetadataEnhancer()
    text = """
    春天来了，万物复苏。
    花儿开放，鸟儿歌唱。
    这是一个美好的季节。
    """
    doc_type = enhancer._classify_document(text)
    assert doc_type == DocType.GENERAL


def test_detect_language_chinese() -> None:
    """测试中文语言检测"""
    enhancer = MetadataEnhancer()
    text = "这是一个中文文档，包含很多中文字符。"
    language = enhancer._detect_language(text)
    assert language == "zh"


def test_detect_language_english() -> None:
    """测试英文语言检测"""
    enhancer = MetadataEnhancer()
    text = "This is an English document with many English words."
    language = enhancer._detect_language(text)
    assert language == "en"


def test_detect_language_mixed() -> None:
    """测试混合语言检测"""
    enhancer = MetadataEnhancer()
    text = "这是一个 mixed 语言 document，包含中文和 English。"
    language = enhancer._detect_language(text)
    assert language in ["zh-en", "zh", "en"]


def test_extract_section_hierarchy_markdown() -> None:
    """测试 Markdown 章节标题提取"""
    enhancer = MetadataEnhancer()
    text = """
    # 第一章 引言
    
    这是引言内容。
    
    ## 1.1 研究背景
    
    这是研究背景。
    
    ### 1.1.1 国内现状
    
    这是国内现状。
    
    ## 1.2 研究意义
    
    这是研究意义。
    """
    sections = enhancer._extract_section_hierarchy(text)
    
    assert len(sections) >= 4
    assert sections[0]["level"] == "1"
    assert "引言" in sections[0]["title"]
    assert sections[1]["level"] == "2"


def test_extract_section_hierarchy_numbered() -> None:
    """测试编号章节标题提取"""
    enhancer = MetadataEnhancer()
    text = """
    1 概述
    
    1.1 项目背景
    
    1.2.1 技术架构
    
    2 系统设计
    
    2.1 需求分析
    """
    sections = enhancer._extract_section_hierarchy(text)
    
    assert len(sections) >= 5
    assert sections[0]["level"] == "1"
    assert sections[2]["level"] == "3"


def test_extract_section_hierarchy_chinese_format() -> None:
    """测试中文格式章节提取"""
    enhancer = MetadataEnhancer()
    text = """
    第一章 总则
    
    第一节 一般规定
    
    第二章 分则
    """
    sections = enhancer._extract_section_hierarchy(text)
    
    assert len(sections) >= 3
    assert all(s["level"] == "1" for s in sections)


def test_enhance_full_metadata() -> None:
    """测试完整元数据增强"""
    enhancer = MetadataEnhancer(max_keywords=5)
    text = """
    # Python API 使用指南
    
    本文档介绍如何使用我们的 Python SDK。
    
    ## 安装
    
    ```bash
    pip install rag-client
    ```
    
    ## 快速开始
    
    ```python
    from rag_client import Client
    
    client = Client(api_key="your-key")
    response = client.query("hello")
    ```
    
    ## API 参考
    
    详细的 API 文档请参考官方文档。
    """
    metadata = enhancer.enhance(text)
    
    assert isinstance(metadata, EnhancedMetadata)
    assert len(metadata.keywords) <= 5
    assert metadata.doc_type in [DocType.CODE, DocType.TECHNICAL]
    assert metadata.language in ["zh", "zh-en"]
    assert metadata.word_count > 0
    assert metadata.sentence_count > 0
    assert len(metadata.section_hierarchy) >= 3


def test_to_dict() -> None:
    """测试元数据转字典"""
    enhancer = MetadataEnhancer()
    metadata = EnhancedMetadata(
        keywords=["test", "keyword"],
        doc_type=DocType.TECHNICAL,
        language="zh",
        word_count=100,
        sentence_count=10,
        avg_sentence_length=10.0,
        section_hierarchy=[{"level": "1", "title": "Test", "marker": "#"}],
    )
    
    result = enhancer.to_dict(metadata)
    
    assert result["keywords"] == ["test", "keyword"]
    assert result["doc_type"] == "technical_docs"
    assert result["language"] == "zh"
    assert result["word_count"] == 100
    assert result["sentence_count"] == 10
    assert len(result["section_hierarchy"]) == 1


def test_metadata_max_keywords() -> None:
    """测试最大关键词数量限制"""
    enhancer = MetadataEnhancer(max_keywords=3)
    text = """
    Machine learning, deep learning, neural networks, artificial intelligence,
    data science, statistics, algorithms, programming, python, tensorflow.
    """
    keywords = enhancer._extract_keywords(text)
    
    assert len(keywords) <= 3


def test_empty_text() -> None:
    """测试空文本处理"""
    enhancer = MetadataEnhancer()
    metadata = enhancer.enhance("")
    
    assert metadata.keywords == []
    assert metadata.doc_type == DocType.GENERAL
    assert metadata.language == "unknown"
    assert metadata.word_count == 0
    assert metadata.sentence_count == 0
