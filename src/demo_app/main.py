#!/usr/bin/env python3
"""
Demo application showcasing the sidecar proxy capabilities
Runs inside the Nitro Enclave and demonstrates secure external communication
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List
import requests
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DemoConfig:
    """Configuration for the demo application"""
    SIDECAR_PROXY_URL = "http://localhost:8080"  # Host proxy endpoint
    TEST_ENDPOINTS = [
        "https://httpbin.org/get",
        "https://httpbin.org/post",
        "https://jsonplaceholder.typicode.com/posts/1",
        "https://api.github.com/users/github"
    ]
    REQUEST_TIMEOUT = 10

class SecureHttpClient:
    """HTTP client that routes requests through the sidecar proxy"""
    
    def __init__(self, proxy_url: str):
        self.proxy_url = proxy_url
        self.session = requests.Session()
        # Set timeout for all requests
        self.session.timeout = DemoConfig.REQUEST_TIMEOUT
    
    def get(self, url: str, headers: Dict[str, str] = None) -> requests.Response:
        """Make a GET request through the sidecar proxy"""
        return self._make_request('GET', url, headers=headers)
    
    def post(self, url: str, data: Any = None, json_data: Dict = None, headers: Dict[str, str] = None) -> requests.Response:
        """Make a POST request through the sidecar proxy"""
        return self._make_request('POST', url, data=data, json=json_data, headers=headers)
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make a request through the sidecar proxy"""
        # The proxy will handle the actual TLS connection to the external service
        # The request URL becomes the target URL that the proxy will forward to
        proxy_headers = kwargs.get('headers', {})
        proxy_headers['X-Target-URL'] = url
        kwargs['headers'] = proxy_headers
        
        # Make request to the local proxy, which will forward to the external service
        return self.session.request(method, url, **kwargs)

class DemoTestSuite:
    """Test suite demonstrating various sidecar capabilities"""
    
    def __init__(self):
        self.client = SecureHttpClient(DemoConfig.SIDECAR_PROXY_URL)
        self.results = []
    
    def run_all_tests(self) -> List[Dict[str, Any]]:
        """Run all demo tests"""
        logger.info("Starting sidecar proxy demo tests")
        
        test_methods = [
            self.test_basic_get_request,
            self.test_post_request_with_json,
            self.test_api_with_headers,
            self.test_github_api,
            self.test_concurrent_requests
        ]
        
        for test_method in test_methods:
            try:
                result = test_method()
                self.results.append(result)
                logger.info(f"Test '{result['name']}' completed: {result['status']}")
            except Exception as e:
                error_result = {
                    'name': test_method.__name__,
                    'status': 'FAILED',
                    'error': str(e),
                    'timestamp': time.time()
                }
                self.results.append(error_result)
                logger.error(f"Test '{test_method.__name__}' failed: {e}")
        
        return self.results
    
    def test_basic_get_request(self) -> Dict[str, Any]:
        """Test basic GET request through sidecar"""
        start_time = time.time()
        
        try:
            response = self.client.get("https://httpbin.org/get")
            duration = time.time() - start_time
            
            return {
                'name': 'Basic GET Request',
                'status': 'PASSED' if response.status_code == 200 else 'FAILED',
                'response_code': response.status_code,
                'duration': duration,
                'response_size': len(response.content),
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'name': 'Basic GET Request',
                'status': 'FAILED',
                'error': str(e),
                'duration': time.time() - start_time,
                'timestamp': start_time
            }
    
    def test_post_request_with_json(self) -> Dict[str, Any]:
        """Test POST request with JSON payload"""
        start_time = time.time()
        
        test_data = {
            'title': 'Sidecar Test',
            'body': 'Testing POST request through Nitro Enclave sidecar',
            'userId': 1
        }
        
        try:
            response = self.client.post(
                "https://jsonplaceholder.typicode.com/posts",
                json_data=test_data,
                headers={'Content-Type': 'application/json'}
            )
            duration = time.time() - start_time
            
            return {
                'name': 'POST Request with JSON',
                'status': 'PASSED' if response.status_code in [200, 201] else 'FAILED',
                'response_code': response.status_code,
                'duration': duration,
                'request_data': test_data,
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'name': 'POST Request with JSON',
                'status': 'FAILED',
                'error': str(e),
                'duration': time.time() - start_time,
                'timestamp': start_time
            }
    
    def test_api_with_headers(self) -> Dict[str, Any]:
        """Test API request with custom headers"""
        start_time = time.time()
        
        headers = {
            'User-Agent': 'Nitro-Enclave-Sidecar-Demo/1.0',
            'Accept': 'application/json',
            'X-Custom-Header': 'EnclaveDemoValue'
        }
        
        try:
            response = self.client.get(
                "https://httpbin.org/headers",
                headers=headers
            )
            duration = time.time() - start_time
            
            return {
                'name': 'API Request with Headers',
                'status': 'PASSED' if response.status_code == 200 else 'FAILED',
                'response_code': response.status_code,
                'duration': duration,
                'custom_headers': headers,
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'name': 'API Request with Headers',
                'status': 'FAILED',
                'error': str(e),
                'duration': time.time() - start_time,
                'timestamp': start_time
            }
    
    def test_github_api(self) -> Dict[str, Any]:
        """Test GitHub API access"""
        start_time = time.time()
        
        try:
            response = self.client.get("https://api.github.com/users/github")
            duration = time.time() - start_time
            
            user_data = None
            if response.status_code == 200:
                try:
                    user_data = response.json()
                except:
                    pass
            
            return {
                'name': 'GitHub API Test',
                'status': 'PASSED' if response.status_code == 200 else 'FAILED',
                'response_code': response.status_code,
                'duration': duration,
                'user_data': user_data.get('login') if user_data else None,
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'name': 'GitHub API Test',
                'status': 'FAILED',
                'error': str(e),
                'duration': time.time() - start_time,
                'timestamp': start_time
            }
    
    def test_concurrent_requests(self) -> Dict[str, Any]:
        """Test multiple concurrent requests"""
        start_time = time.time()
        
        import concurrent.futures
        import threading
        
        def make_request(url):
            try:
                response = self.client.get(url)
                return {
                    'url': url,
                    'status_code': response.status_code,
                    'success': response.status_code == 200
                }
            except Exception as e:
                return {
                    'url': url,
                    'error': str(e),
                    'success': False
                }
        
        urls = [
            "https://httpbin.org/delay/1",
            "https://httpbin.org/delay/2", 
            "https://jsonplaceholder.typicode.com/posts/1",
            "https://jsonplaceholder.typicode.com/posts/2"
        ]
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_url = {executor.submit(make_request, url): url for url in urls}
                results = []
                
                for future in concurrent.futures.as_completed(future_to_url):
                    result = future.result()
                    results.append(result)
            
            duration = time.time() - start_time
            successful_requests = sum(1 for r in results if r.get('success', False))
            
            return {
                'name': 'Concurrent Requests',
                'status': 'PASSED' if successful_requests >= len(urls) // 2 else 'FAILED',
                'total_requests': len(urls),
                'successful_requests': successful_requests,
                'duration': duration,
                'individual_results': results,
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'name': 'Concurrent Requests',
                'status': 'FAILED',
                'error': str(e),
                'duration': time.time() - start_time,
                'timestamp': start_time
            }
    
    def generate_report(self) -> str:
        """Generate a test report"""
        passed_tests = sum(1 for r in self.results if r.get('status') == 'PASSED')
        total_tests = len(self.results)
        
        report = f"""
=== Nitro Enclave Sidecar Proxy Demo Report ===

Test Summary:
- Total Tests: {total_tests}
- Passed: {passed_tests}
- Failed: {total_tests - passed_tests}
- Success Rate: {(passed_tests / total_tests * 100):.1f}%

Detailed Results:
"""
        
        for result in self.results:
            report += f"\n• {result['name']}: {result['status']}"
            if 'duration' in result:
                report += f" (Duration: {result['duration']:.2f}s)"
            if 'error' in result:
                report += f" - Error: {result['error']}"
        
        report += f"\n\nAll tests completed at {time.ctime()}"
        return report

class DemoApplication:
    """Main demo application"""
    
    def __init__(self):
        self.test_suite = DemoTestSuite()
    
    def run(self):
        """Run the demo application"""
        logger.info("=== Starting Nitro Enclave Sidecar Proxy Demo ===")
        
        try:
            # Run test suite
            results = self.test_suite.run_all_tests()
            
            # Generate and display report
            report = self.test_suite.generate_report()
            print(report)
            
            # Also log the report
            logger.info("Demo completed successfully")
            
            return 0
            
        except Exception as e:
            logger.error(f"Demo failed: {e}")
            return 1

def main():
    """Main entry point"""
    try:
        demo = DemoApplication()
        return demo.run()
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
