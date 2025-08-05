import json
import os
import boto3
from botocore.exceptions import ClientError

SUITS = ['C', 'D', 'H', 'S']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def lambda_handler(event, context):
    """
    WebSocket handler for playing a card
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-id",
            "routeKey": "$connect" | "$disconnect" | "playCard"
        },
        "body": "{\"roomId\": \"room-id\", \"userId\": \"user-id\", \"card\": \"AH\"}"
    }
    """
    try:
        # Extract connection ID for potential future use
        connection_id = event.get('requestContext', {}).get('connectionId')
        route_key = event.get('requestContext', {}).get('routeKey')
        
        # Handle different route keys
        if route_key == '$connect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Connected'})
            }
        elif route_key == '$disconnect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Disconnected'})
            }
        elif route_key != 'playCard':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid route key'})
            }
        
        # Parse the message body
        body = event.get('body')
        if not body:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing request body'})
            }
        
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract parameters
        user_id = body.get('userId')
        room_id = body.get('roomId')
        card = body.get('card')
        
        if not user_id or not room_id or not card:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId, roomId, and card required'})
            }
        
        # Validate card format (e.g., "AH" for Ace of Hearts)
        if len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Invalid card format. Use format like "AH" (Ace of Hearts). Valid ranks: {", ".join(RANKS)}, Valid suits: {", ".join(SUITS)}'})
            }
        
        # Fetch room
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})
            }
        
        dynamodb = boto3.resource('dynamodb')
        room_table = dynamodb.Table(room_table_name)
        room_result = room_table.get_item(Key={'roomId': room_id})
        
        if 'Item' not in room_result:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Room does not exist'})
            }
        
        room_item = room_result['Item']
        
        # Check if room is in playing phase
        if room_item['state'] != 'playing':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Room is not in playing phase'})
            }
        
        # Check if it's the user's turn
        game_data = room_item.get('gameData', {})
        current_turn = game_data.get('turn')
        
        if current_turn != user_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Not your turn to play'})
            }
        
        # Find user's seat
        user_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                user_seat = seat
                break
        
        if not user_seat:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'User not found in room'})
            }
        
        # Check if user has the card in their hand
        hands = game_data.get('hands', {})
        user_hand = hands.get(user_seat, [])
        
        if card not in user_hand:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Card not in your hand'})
            }
        
        # Check if card follows suit (if not leading)
        current_trick = game_data.get('currentTrick', [])
        if current_trick:
            # Not leading, must follow suit if possible
            lead_suit = current_trick[0]['card'][1]  # Get suit of first card
            played_suit = card[1]
            
            if played_suit != lead_suit:
                # Check if player has cards of the led suit
                has_led_suit = any(c[1] == lead_suit for c in user_hand)
                if has_led_suit:
                    return {
                        'statusCode': 400,
                        'body': json.dumps({'error': f'Must follow suit. Lead suit is {lead_suit}'})
                    }
        
        # Remove card from hand
        user_hand.remove(card)
        hands[user_seat] = user_hand
        
        # Add card to current trick
        if 'currentTrick' not in game_data:
            game_data['currentTrick'] = []
        
        play_entry = {
            'seat': user_seat,
            'card': card,
            'timestamp': int(boto3.client('sts').get_caller_identity()['Account'])  # Simple timestamp
        }
        
        game_data['currentTrick'].append(play_entry)
        
        # Determine next turn
        seats = ['N', 'E', 'S', 'W']
        current_seat_index = seats.index(user_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        next_player = room_item['seats'][next_seat]
        
        game_data['turn'] = next_player
        
        # Check if trick is complete (4 cards played)
        if len(game_data['currentTrick']) == 4:
            # Determine winner of the trick
            winner = determine_trick_winner(game_data['currentTrick'])
            
            # Add trick to completed tricks
            if 'tricks' not in game_data:
                game_data['tricks'] = []
            
            game_data['tricks'].append({
                'cards': game_data['currentTrick'],
                'winner': winner
            })
            
            # Clear current trick
            game_data['currentTrick'] = []
            
            # Set next turn to winner
            game_data['turn'] = room_item['seats'][winner]
            
            # Check if hand is complete (13 tricks)
            if len(game_data['tricks']) == 13:
                # Hand is complete, determine winner
                game_data['currentPhase'] = 'completed'
                room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'action': 'playCard',
                'success': True,
                'play': play_entry,
                'nextTurn': next_player,
                'gameData': game_data,
                'message': f'Card {card} played successfully'
            })
        }
        
    except ClientError as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': e.response['Error']['Message']})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def determine_trick_winner(trick):
    """
    Determine the winner of a trick based on Bridge rules
    """
    if not trick:
        return None
    
    # Get the lead suit
    lead_suit = trick[0]['card'][1]
    
    # Find the highest card of the lead suit
    highest_card = None
    highest_rank_value = -1
    
    for play in trick:
        card = play['card']
        suit = card[1]
        rank = card[0]
        
        # Only consider cards of the lead suit
        if suit == lead_suit:
            rank_value = RANKS.index(rank)
            if rank_value > highest_rank_value:
                highest_rank_value = rank_value
                highest_card = play
    
    return highest_card['seat'] if highest_card else trick[0]['seat'] 