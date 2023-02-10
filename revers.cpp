#include<iostream>
using namespace std;
int main()
{
	//reverse of any three digit number
	int a=456;
	int b=a/100;
	int c=a%100;
	int d=c/10;
	int e=c%10;
	
	int f = (e*100) + (d*10) + (b*1);
	cout<<"Reverse of "<<a<<" is "<<f;
	//output will be 654
	return 0;
}
