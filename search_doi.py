import requests
from habanero import Crossref
from Bio import Entrez
import json
import re
import os
import ssl
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
import csv
import traceback
import urllib3

class DOISearcher:
    def __init__(self, use_cache: bool = True, cache_dir: str = '.cache'):
        # API URLs
        self.crossref_api_url = "https://api.crossref.org/works/"
        self.pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # 配置
        self.email = "your.email@example.com"  # 替换为你的邮箱
        Entrez.email = self.email
        Entrez.tool = "DOISearcher"
        
        # 禁用SSL警告和验证
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 缓存设置
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(days=7)
        
        # DOI验证
        self.doi_pattern = re.compile(r'^10\.\d{4,9}/[-._;()/:\w]+$')
        
        # 创建缓存目录
        if self.use_cache and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
        # 搜索历史
        self.search_history = []
        
        # 请求延迟
        self.last_request_time = 0
        self.min_delay = 1.0

    def validate_doi(self, doi: str) -> bool:
        """验证DOI格式"""
        return bool(doi and isinstance(doi, str) and self.doi_pattern.match(doi))

    def _get_cache_path(self, doi: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{doi.replace('/', '_')}.json")

    def _get_from_cache(self, doi: str) -> Optional[Dict]:
        """从缓存获取数据"""
        if not self.use_cache:
            return None
            
        cache_path = self._get_cache_path(doi)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cached_time = datetime.fromisoformat(data['timestamp'])
                    if datetime.now() - cached_time <= self.cache_ttl:
                        return data['data']
            except Exception as e:
                print(f"读取缓存出错: {e}")
        return None

    def _save_to_cache(self, doi: str, data: Dict) -> None:
        """保存数据到缓存"""
        if not self.use_cache:
            return
            
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            with open(self._get_cache_path(doi), 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存缓存出错: {e}")

    def _wait_between_requests(self):
        """控制请求频率"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def get_paper_info(self, doi: str) -> Optional[Dict]:
        """获取论文信息"""
        if not self.validate_doi(doi):
            print(f"无效的DOI格式: {doi}")
            return None

        # 检查缓存
        cached_data = self._get_from_cache(doi)
        if cached_data:
            return cached_data

        self._wait_between_requests()
        
        try:
            # 从CrossRef获取数据
            cr = Crossref()
            work = cr.works(ids=doi)
            
            if 'message' not in work:
                print("未找到文章信息")
                return None
                
            data = work['message']
            self._save_to_cache(doi, data)
            return data
            
        except Exception as e:
            print(f"获取论文信息时出错: {e}")
            traceback.print_exc()
            return None

    def get_author_research(self, author_name: str, max_results: int = 10) -> Dict:
        """获取作者研究信息"""
        self._wait_between_requests()
        
        try:
            # 搜索PubMed
            handle = Entrez.esearch(
                db="pubmed",
                term=f"{author_name}[Author]",
                retmax=max_results,
                sort="date"
            )
            record = Entrez.read(handle)
            handle.close()

            if not record['IdList']:
                return {'papers': [], 'total': 0}

            # 获取文章详情
            self._wait_between_requests()
            handle = Entrez.efetch(
                db="pubmed",
                id=','.join(record['IdList']),
                rettype="medline",
                retmode="text"
            )
            
            papers = []
            for paper in handle.read().split('\n\n'):
                if not paper.strip():
                    continue
                    
                title = None
                journal = None
                year = None
                
                for line in paper.split('\n'):
                    if line.startswith('TI  -'):
                        title = line[6:].strip()
                    elif line.startswith('TA  -'):
                        journal = line[6:].strip()
                    elif line.startswith('DP  -'):
                        year = line[6:].strip()[:4]
                        
                if title:
                    papers.append({
                        'title': title,
                        'journal': journal,
                        'year': year
                    })
            
            handle.close()
            return {
                'papers': papers,
                'total': int(record['Count'])
            }
            
        except Exception as e:
            print(f"获取作者研究信息时出错: {e}")
            traceback.print_exc()
            return {'papers': [], 'total': 0}

    def find_authors(self, doi: str) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
        """查找论文作者信息"""
        paper_info = self.get_paper_info(doi)
        if not paper_info or 'author' not in paper_info:
            return None, None, None

        authors = paper_info['author']
        
        # 获取第一作者
        first_author = None
        if authors:
            first = authors[0]
            first_author = f"{first.get('given', '')} {first.get('family', '')}".strip()

        # 获取通讯作者
        corresponding_author = None
        for author in reversed(authors):
            if author.get('sequence') == 'additional' and \
               author.get('contributor-role', {}).get('function') == 'corresponding':
                corresponding_author = f"{author.get('given', '')} {author.get('family', '')}".strip()
                break
        
        # 如果没有明确标记，使用最后一位作者
        if not corresponding_author and authors:
            last = authors[-1]
            corresponding_author = f"{last.get('given', '')} {last.get('family', '')}".strip()

        # 获取通讯作者研究信息
        research_info = None
        if corresponding_author:
            print(f"\n正在获取通讯作者 {corresponding_author} 的研究信息...")
            research_info = self.get_author_research(corresponding_author)

        # 记录搜索历史
        self.search_history.append({
            'doi': doi,
            'first_author': first_author,
            'corresponding_author': corresponding_author,
            'timestamp': datetime.now().isoformat(),
            'research_info': research_info
        })

        return first_author, corresponding_author, research_info

    def export_history(self, filename: str = None) -> None:
        """导出搜索历史"""
        if not self.search_history:
            print("没有可导出的搜索历史")
            return

        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'search_history_{timestamp}.csv'

        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'DOI',
                    '第一作者',
                    '通讯作者',
                    '查询时间',
                    '发表论文数',
                    '最近论文'
                ])

                for record in self.search_history:
                    recent_papers = ''
                    if record.get('research_info', {}).get('papers'):
                        papers = record['research_info']['papers'][:3]
                        recent_papers = '; '.join(
                            f"{p['title']} ({p['year']})" for p in papers
                        )

                    writer.writerow([
                        record['doi'],
                        record['first_author'],
                        record['corresponding_author'],
                        record['timestamp'],
                        record.get('research_info', {}).get('total', 0),
                        recent_papers
                    ])

            print(f"\n搜索历史已导出到: {filename}")
            
        except Exception as e:
            print(f"导出历史记录时出错: {e}")
            traceback.print_exc()

def main():
    searcher = DOISearcher()
    
    print("\n=== DOI文献作者搜索工具 ===")
    print("命令说明:")
    print("  q - 退出程序")
    print("  e - 导出搜索历史")
    print("  h - 显示帮助信息")
    
    while True:
        try:
            doi = input("\n请输入DOI (或输入命令): ").strip()
            
            if doi.lower() == 'q':
                if searcher.search_history:
                    if input("\n是否导出搜索历史? (y/n): ").lower() == 'y':
                        searcher.export_history()
                print("\n感谢使用！")
                break
                
            elif doi.lower() == 'e':
                searcher.export_history()
                continue
                
            elif doi.lower() == 'h':
                print("\n命令说明:")
                print("  q - 退出程序")
                print("  e - 导出搜索历史")
                print("  h - 显示帮助信息")
                print("\nDOI示例: 10.1038/s41586-020-2169-0")
                continue

            if not doi:
                print("DOI不能为空")
                continue

            print("\n正在搜索...")
            first_author, corresponding_author, research_info = searcher.find_authors(doi)

            if first_author or corresponding_author:
                print(f"\n第一作者: {first_author or '未找到'}")
                print(f"通讯作者: {corresponding_author or '未找到'}")
                
                if research_info and research_info['papers']:
                    print(f"\n发表论文总数: {research_info['total']}")
                    print("\n最近发表的论文:")
                    for i, paper in enumerate(research_info['papers'][:5], 1):
                        print(f"{i}. [{paper['year']}] {paper['title']}")
                        if paper['journal']:
                            print(f"   期刊: {paper['journal']}")
            else:
                print("\n未找到作者信息，请检查DOI是否正确")
                
        except KeyboardInterrupt:
            print("\n\n程序被中断")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            traceback.print_exc()
            print("请重试或输入 'q' 退出")

if __name__ == "__main__":
    main() 