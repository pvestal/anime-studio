#!/usr/bin/env python3
'''
Make anime service communicate through Echo Brain for orchestration
'''

import requests
import json

class EchoIntegration:
    def __init__(self, echo_url='http://localhost:8309'):
        self.echo_url = echo_url
        
    async def request_quality_assessment(self, video_path, prompt, metadata):
        '''Request quality assessment through Echo'''
        task = {
            'name': 'quality_assessment',
            'type': 'LEARNING',
            'priority': 'NORMAL',
            'data': {
                'video_path': video_path,
                'prompt': prompt,
                'metadata': metadata
            }
        }
        
        response = requests.post(f'{self.echo_url}/api/tasks/add', json=task)
        return response.json()
        
    async def report_generation_complete(self, generation_id, output_path):
        '''Report completion to Echo for orchestration'''
        response = requests.post(f'{self.echo_url}/api/evaluate', json={
            'task_id': generation_id,
            'output': output_path,
            'service': 'anime_generation'
        })
        return response.json()
        
    async def request_feedback_collection(self, generation_id, quality_score):
        '''Ask Echo to collect feedback'''
        if quality_score < 70:
            task = {
                'name': 'collect_feedback',
                'type': 'OPTIMIZATION',
                'data': {
                    'generation_id': generation_id,
                    'quality_score': quality_score,
                    'action': 'improve_prompt'
                }
            }
            response = requests.post(f'{self.echo_url}/api/tasks/add', json=task)
            return response.json()
