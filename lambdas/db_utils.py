import os
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

class DatabaseUtils:
    """
    Utility class for common DynamoDB operations
    """
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
    
    def get_table(self, table_name_env: str):
        """
        Get DynamoDB table by environment variable name
        """
        table_name = os.environ.get(table_name_env)
        print(f"Getting table for env var {table_name_env}: {table_name}")
        if not table_name:
            raise ValueError(f"{table_name_env} environment variable not set")
        return self.dynamodb.Table(table_name)
    
    def update_user_room(self, user_id: str, room_id: str) -> bool:
        """
        Update the user's current room in the connections table
        Returns True if successful, False otherwise
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            # Find the user's connection
            response = connections_table.scan(
                FilterExpression='#userId = :userId AND #status = :status',
                ExpressionAttributeNames={
                    '#userId': 'userId',
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':userId': user_id,
                    ':status': 'connected'
                }
            )
            
            success_count = 0
            for item in response.get('Items', []):
                connection_id = item.get('connectionId')
                if not connection_id or not isinstance(connection_id, str):
                    continue
                
                try:
                    # Since currentRoomId is the sort key, delete old item and create new one
                    old_key = {
                        'connectionId': connection_id, 
                        'currentRoomId': item.get('currentRoomId', 'not-joined')
                    }
                    
                    # Delete the old item
                    connections_table.delete_item(Key=old_key)
                    
                    # Create new item with updated currentRoomId
                    new_item = item.copy()
                    new_item['currentRoomId'] = room_id
                    
                    connections_table.put_item(Item=new_item)
                    success_count += 1
                    
                except ClientError as e:
                    print(f"Error updating connection {connection_id}: {e.response['Error']['Message']}")
                    continue
            
            return success_count > 0
            
        except Exception as e:
            print(f"Error updating user room: {str(e)}")
            return False
    
    def get_room_connections(self, user_ids: List[str], room_id: str) -> List[str]:
        """
        Get active WebSocket connections for users in a specific room
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            connection_ids = []
            for user_id in user_ids:
                if user_id and not user_id.startswith('robot-'):  # Skip robot players
                    response = connections_table.scan(
                        FilterExpression='#status = :status AND #userId = :userId',
                        ExpressionAttributeNames={'#status': 'status', '#userId': 'userId'},
                        ExpressionAttributeValues={':status': 'connected', ':userId': user_id}
                    )
                    connection_ids.extend([item['connectionId'] for item in response.get('Items', [])])
            
            return list(set(connection_ids))  # Remove duplicates
            
        except Exception as e:
            print(f"Error getting room connections: {str(e)}")
            return []
    
    def get_active_room_count(self) -> int:
        """
        Get the count of unique active rooms
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            active_rooms: Set[str] = set()
            
            # Scan all items to get unique room IDs
            response = connections_table.scan()
            
            # Process first batch
            for item in response.get('Items', []):
                room_id = item.get('currentRoomId')
                if room_id and room_id != 'not-joined':
                    active_rooms.add(room_id)
            
            # Continue scanning if there are more items
            while 'LastEvaluatedKey' in response:
                response = connections_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                for item in response.get('Items', []):
                    room_id = item.get('currentRoomId')
                    if room_id and room_id != 'not-joined':
                        active_rooms.add(room_id)
            
            return len(active_rooms)
            
        except Exception as e:
            print(f"Error getting active room count: {str(e)}")
            return 0
    
    def get_active_user_count(self) -> int:
        """
        Get the count of unique active users
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            active_users: Set[str] = set()
            
            # Scan all items to get unique user IDs
            response = connections_table.scan()
            
            # Process first batch
            for item in response.get('Items', []):
                user_id = item.get('userId')
                if user_id and item.get('status') == 'connected':
                    active_users.add(user_id)
            
            # Continue scanning if there are more items
            while 'LastEvaluatedKey' in response:
                response = connections_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                for item in response.get('Items', []):
                    user_id = item.get('userId')
                    if user_id and item.get('status') == 'connected':
                        active_users.add(user_id)
            
            return len(active_users)
            
        except Exception as e:
            print(f"Error getting active user count: {str(e)}")
            return 0
    
    def get_connection_stats(self) -> Dict[str, int]:
        """
        Get both active user count and active room count in a single scan
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            active_rooms: Set[str] = set()
            active_users: Set[str] = set()
            
            # Scan all items to get unique room IDs and user IDs
            response = connections_table.scan()
            
            # Process first batch
            for item in response.get('Items', []):
                # Count active rooms
                room_id = item.get('currentRoomId')
                if room_id and room_id != 'not-joined':
                    active_rooms.add(room_id)
                
                # Count active users
                user_id = item.get('userId')
                if user_id and item.get('status') == 'connected':
                    active_users.add(user_id)
            
            # Continue scanning if there are more items
            while 'LastEvaluatedKey' in response:
                response = connections_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                for item in response.get('Items', []):
                    # Count active rooms
                    room_id = item.get('currentRoomId')
                    if room_id and room_id != 'not-joined':
                        active_rooms.add(room_id)
                    
                    # Count active users
                    user_id = item.get('userId')
                    if user_id and item.get('status') == 'connected':
                        active_users.add(user_id)
            
            return {
                'activeUserCount': len(active_users),
                'activeRoomCount': len(active_rooms)
            }
            
        except Exception as e:
            print(f"Error getting connection stats: {str(e)}")
            return {
                'activeUserCount': 0,
                'activeRoomCount': 0
            }
    
    def find_room_by_id(self, room_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a room by its ID using scan (since we don't have the sort key)
        """
        try:
            room_table = self.get_table('ROOM_TABLE')
            
            response = room_table.scan(
                FilterExpression='roomId = :roomId',
                ExpressionAttributeValues={':roomId': room_id}
            )
            
            if response['Count'] == 0:
                return None
            
            return response['Items'][0]
            
        except Exception as e:
            print(f"Error finding room by ID: {str(e)}")
            return None
    
    def create_connection_record(self, connection_id: str, user_id: str, user_name: str, 
                               request_time: Optional[int] = None) -> bool:
        """
        Create a new connection record in the connections table
        """
        try:
            print(f"Creating connection record for connection_id: {connection_id}, user_id: {user_id}")
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            if not request_time:
                request_time = int(datetime.now().timestamp() * 1000)
            
            connection_record = {
                'connectionId': connection_id,
                'currentRoomId': 'not-joined',  # Sort key - placeholder for new connections
                'connectedAt': request_time,
                'sourceIp': 'unknown',
                'userAgent': 'unknown',
                'status': 'connected',
                'lastActivity': request_time,
                'userId': user_id,
                'userName': user_name
            }
            
            print(f"Connection record to create: {connection_record}")
            connections_table.put_item(Item=connection_record)
            print(f"Successfully created connection record for {connection_id}")
            return True
            
        except Exception as e:
            print(f"Error creating connection record: {str(e)}")
            print(f"Connection ID: {connection_id}, User ID: {user_id}")
            return False
    
    def delete_connection_record(self, connection_id: str, current_room_id: str = 'not-joined') -> bool:
        """
        Delete a connection record from the connections table
        """
        try:
            connections_table = self.get_table('WEBSOCKET_CONNECTIONS_TABLE')
            
            key = {
                'connectionId': connection_id,
                'currentRoomId': current_room_id
            }
            
            connections_table.delete_item(Key=key)
            return True
            
        except Exception as e:
            print(f"Error deleting connection record: {str(e)}")
            return False

# Global instance for easy import
db_utils = DatabaseUtils() 